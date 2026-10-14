/**
 * @file TurretController.ino
 * @brief Nonblocking, pulse-based two-axis bench actuator controller.
 *
 * Read the repository README.md for setup and protocol selection for this
 * sketch. No physical angle, contact, current, or camera feedback is available.
 * VCC is logic; V+ supplies servos. Maintain the wired common ground.
 * A software hold leaves torque applied. Cut servo power if the mechanism binds.
 * Tested source settings are intentionally preserved; no degree mapping exists.
 */
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>
#include <ctype.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

Adafruit_PWMServoDriver pwm;
const int TILT_CHANNEL = 0;
const int PAN_CHANNEL = 1;
const int SDA_PIN = 21;
const int SCL_PIN = 22;
const int PWM_FREQ = 50;

// Arrays use the physical channel as index: tilt=0, pan=1.
// Bracket-only bounds; recheck with the payload. Tilt 1510 is near contact.
const int MIN_US[2] = {400, 420};
const int MAX_US[2] = {1510, 2850};
const int ZERO_US[2] = {1370, 1270};
const char* const AXIS_NAME[2] = {"Tilt", "Pan"};

// Command ramp: 50 us / 20 ms = 2500 us/s.
// This limits the command ramp, not measured shaft speed or physical latency.
const int STEP_US = 50;
const unsigned long STEP_INTERVAL_MS = 20;
// Only managed `m pan tilt` commands use this watchdog. Interactive p/t targets
// are deliberate finite moves and can take longer than this timeout.
const unsigned long MANAGED_TIMEOUT_MS = 500;
bool managedMode = false;
unsigned long lastManagedMs = 0;
static_assert(STEP_US > 0 && STEP_INTERVAL_MS > 0, "Step and interval must be positive.");

int currentUs[2] = {ZERO_US[0], ZERO_US[1]};
int targetUs[2] = {ZERO_US[0], ZERO_US[1]};
unsigned long lastStepMs[2] = {0, 0};
unsigned long acceptedMs[2] = {0, 0};
bool firstStepPending[2] = {false, false};
char inputLine[48];
size_t inputLength = 0;
bool overflowed = false;

void printStatus() {
    // Versioned reply lets the Python adapter verify the firmware before motion.
    Serial.println("PROTO 1 pulse_us managed_pair watchdog_500ms");
    for (int axis = 0; axis < 2; ++axis) {
        Serial.print(AXIS_NAME[axis]);
        Serial.print(": commanded=");
        Serial.print(currentUs[axis]);
        Serial.print(" us, target=");
        Serial.print(targetUs[axis]);
        Serial.println(" us");
    }
}

bool setTarget(int axis, long requestedUs) {
    if (requestedUs < MIN_US[axis] || requestedUs > MAX_US[axis]) {
        Serial.println("Rejected: outside this axis's configured pulse bounds.");
        return false;
    }
    targetUs[axis] = static_cast<int>(requestedUs);
    acceptedMs[axis] = millis();
    firstStepPending[axis] = currentUs[axis] != targetUs[axis];
    Serial.print(AXIS_NAME[axis]);
    Serial.print(" target accepted: ");
    Serial.print(targetUs[axis]);
    Serial.println(" us");
    if (!firstStepPending[axis]) Serial.println("Already at that command (not measured position).");
    return true;
}

void stopMotion() {
    managedMode = false;
    for (int axis = 0; axis < 2; ++axis) {
        targetUs[axis] = currentUs[axis];
        firstStepPending[axis] = false;
    }
    Serial.println("Stopped stepping. Servos still hold their last commands.");
    printStatus();
}

void processLine(char* line) {
    while (isspace(static_cast<unsigned char>(*line))) ++line;
    size_t length = strlen(line);
    while (length > 0 && isspace(static_cast<unsigned char>(line[length - 1])))
        line[--length] = '\0';
    if (!length) return;
    if (strcmp(line, "?") == 0) { printStatus(); return; }
    if (strcmp(line, "0") == 0) {
        managedMode = false;
        setTarget(TILT_CHANNEL, ZERO_US[TILT_CHANNEL]);
        setTarget(PAN_CHANNEL, ZERO_US[PAN_CHANNEL]);
        return;
    }
    // The pair is transactional: validate both numbers before changing either
    // target, so one bad tilt value cannot leave a new pan target half-applied.
    if (line[0] == 'm' && line[1] == ' ') {
        char* end = nullptr;
        errno = 0;
        const long pan = strtol(line + 2, &end, 10);
        if (errno == ERANGE || end == line + 2 || !isspace(static_cast<unsigned char>(*end))) {
            Serial.println("Rejected: use m PAN_US TILT_US");
            return;
        }
        char* second = end;
        const long tilt = strtol(second, &end, 10);
        if (errno == ERANGE || second == end || *end != '\0' ||
            pan < MIN_US[PAN_CHANNEL] || pan > MAX_US[PAN_CHANNEL] ||
            tilt < MIN_US[TILT_CHANNEL] || tilt > MAX_US[TILT_CHANNEL]) {
            Serial.println("Rejected: pair must contain two in-range integer pulses.");
            return;
        }
        lastManagedMs = millis();
        managedMode = true;
        // A repeated target refreshes the watchdog without restarting timing
        // measurements or filling the serial connection with duplicate output.
        if (targetUs[PAN_CHANNEL] != pan) setTarget(PAN_CHANNEL, pan);
        if (targetUs[TILT_CHANNEL] != tilt) setTarget(TILT_CHANNEL, tilt);
        return;
    }
    if ((line[0] != 'p'  && line[0] != 't') || line[1] != ' ') {
        Serial.println("Use p 1500, t 1200, x, 0, or ?; finish targets with Newline.");
        return;
    }
    char* end = nullptr;
    errno = 0;
    const long pulse = strtol(line + 2, &end, 10);
    if (end == line + 2 || *end != '\0' || errno == ERANGE) {
        Serial.println("Rejected: enter a whole number of microseconds.");
        return;
    }
    // A rejected manual request must not disable an existing managed timeout.
    if (setTarget(line[0] == 'p' ? PAN_CHANNEL : TILT_CHANNEL, pulse))
        managedMode = false;
}

void handleSerial() {
    // Bounded, nonblocking input processing keeps motion updates running.
    for (int count = 0; count < 64 && Serial.available() > 0; ++count) {
        const char c = Serial.read();
        // Stop acts immediately on receipt, even before a newline.
        if (c == 'x' || c == 'X') {
            inputLength = 0;
            overflowed = false;
            stopMotion();
            while (Serial.available() > 0) Serial.read();
            return;
        }
        if (c == '\r') continue;
        if (c == '\n') {
            if (overflowed) Serial.println("Rejected: command too long.");
            else {
                inputLine[inputLength] = '\0';
                processLine(inputLine);
            }
            inputLength = 0;
            overflowed = false;
        } else if (!overflowed) {
            if (inputLength < sizeof(inputLine) - 1) inputLine[inputLength++] = c;
            else overflowed = true;
        }
    }
}

void updateAxis(int axis) {
    if (currentUs[axis] == targetUs[axis]) return;
    const unsigned long now = millis();
    if (now - lastStepMs[axis] < STEP_INTERVAL_MS) return;
    lastStepMs[axis] = now;
    const int difference = targetUs[axis] - currentUs[axis];
    const int change = difference > STEP_US ? STEP_US
                     : difference < -STEP_US ? -STEP_US : difference;
    currentUs[axis] += change; // Final step shortens to avoid overshooting.
    pwm.writeMicroseconds(axis, currentUs[axis]);
    const unsigned long elapsed = millis() - acceptedMs[axis];
    if (firstStepPending[axis]) {
        firstStepPending[axis] = false;
        Serial.print(AXIS_NAME[axis]);
        Serial.print(" first output update after acceptance: ");
        Serial.print(elapsed);
        Serial.println(" ms");
    }
    if (currentUs[axis] == targetUs[axis]) {
        Serial.print(AXIS_NAME[axis]);
        Serial.print(" target command reached after ");
        Serial.print(elapsed);
        Serial.println(" ms; physical arrival is NOT measured.");
    }
}

void setup() {
    Serial.begin(115200);
    Wire.begin(SDA_PIN, SCL_PIN);
    if (!pwm.begin()) {
        Serial.println("PCA9685 initialization failed.");
        while (true) delay(1000);
    }
    pwm.setPWMFreq(PWM_FREQ);
    // First movement is directly to reference: initial shaft angles are unknown.
    for (int axis = 0; axis < 2; ++axis) {
        pwm.writeMicroseconds(axis, currentUs[axis]);
        lastStepMs[axis] = millis();
    }
    Serial.println("Manual targets: 115200 baud, Newline.");
    Serial.println("p 1500 = pan target | t 1200 = tilt target (microseconds)");
    Serial.println("x = stop and hold | 0 = ramp both to reference | ? = status");
    Serial.println("m PAN_US TILT_US = managed pair; refresh within 500 ms or hold.");
    Serial.println("Timing covers firmware commands, not USB delay or physical motion.");
    printStatus();
}

void loop() {
    handleSerial();
    // This check continues while serial input is incomplete. Unsigned elapsed
    // subtraction also works when millis() wraps (for these short intervals).
    if (managedMode && millis() - lastManagedMs >= MANAGED_TIMEOUT_MS) {
        stopMotion();
        Serial.println("WATCHDOG: managed commands timed out; holding last outputs.");
    }
    updateAxis(TILT_CHANNEL);
    updateAxis(PAN_CHANNEL);
}
