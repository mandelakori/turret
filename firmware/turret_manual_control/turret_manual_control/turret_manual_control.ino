/**
 * @file turret_manual_control.ino
 * @brief Manual pulse-coordinate control with an adjustable command ramp.
 *
 * Serial Monitor: 115200 baud, Newline. Coordinates are PAN_US, TILT_US;
 * speed is microseconds of pulse change per second, not degrees/second.
 * Read README.md for examples, equations, calibration and verification notes.
 * No measured position, collision detection or physical arrival feedback exists.
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

// Array indices are physical PCA9685 channels: tilt first, pan second.
// Retain the established pulse limits and reference values.
constexpr int MIN_US[2] = {400, 420};
constexpr int MAX_US[2] = {1510, 2850};
constexpr int ZERO_US[2] = {1370, 1270};
const char* const AXIS_NAME[2] = {"Tilt", "Pan"};
static_assert(MIN_US[0] <= ZERO_US[0] && ZERO_US[0] <= MAX_US[0],
              "Tilt reference must be inside its bounds.");
static_assert(MIN_US[1] <= ZERO_US[1] && ZERO_US[1] <= MAX_US[1],
              "Pan reference must be inside its bounds.");
static_assert(MIN_US[0] > 0 && MIN_US[1] > 0 &&
              MAX_US[0] < 1000000 / PWM_FREQ && MAX_US[1] < 1000000 / PWM_FREQ,
              "Pulse bounds must fit inside a PWM period.");

// A 20 ms update interval matches the nominal 50 Hz PWM period.
// A 50 us step at 20 ms is equivalent to 2500 us/s. This is the
// default and maximum command rate; start with s 200 for a small bench move.
const unsigned long STEP_INTERVAL_MS = 20;
const long MIN_SPEED_US_PER_S = 1;
const long MAX_SPEED_US_PER_S = 2500;
const long DEFAULT_SPEED_US_PER_S = 2500;
static_assert(STEP_INTERVAL_MS > 0, "Update interval must be positive.");
static_assert(MIN_SPEED_US_PER_S > 0 &&
              MIN_SPEED_US_PER_S <= DEFAULT_SPEED_US_PER_S &&
              DEFAULT_SPEED_US_PER_S <= MAX_SPEED_US_PER_S,
              "Default speed must be inside its bounds.");
static_assert(MAX_SPEED_US_PER_S <= 2147483647L / STEP_INTERVAL_MS,
              "Scaled ramp increment must fit in a 32-bit long.");
long speedUsPerSecond = DEFAULT_SPEED_US_PER_S;

// currentUs is the last integer pulse request sent to the PWM driver.
// targetUs is the requested endpoint. Neither represents measured shaft angle.
int currentUs[2] = {ZERO_US[0], ZERO_US[1]};
int targetUs[2] = {ZERO_US[0], ZERO_US[1]};

// Fixed-point state stores thousandths of a microsecond. Fractional changes
// accumulate instead of being lost when a slow speed gives <1 us per update.
// Example: 25 us/s * 20 ms = 500 scaled units = 0.5 us per update.
long rampMilliUs[2] = {ZERO_US[0] * 1000L, ZERO_US[1] * 1000L};
unsigned long lastStepMs[2] = {0, 0};
unsigned long acceptedMs[2] = {0, 0};
bool firstStepPending[2] = {false, false};
char inputLine[48];
size_t inputLength = 0;
bool overflowed = false;

void printStatus() {
    Serial.print("Command speed: ");
    Serial.print(speedUsPerSecond);
    Serial.println(" us/s per moving axis");
    for (int axis = 0; axis < 2; ++axis) {
        Serial.print(AXIS_NAME[axis]);
        Serial.print(": commanded=");
        Serial.print(currentUs[axis]);
        Serial.print(" us, target=");
        Serial.print(targetUs[axis]);
        Serial.println(" us");
    }
}

bool pulseInBounds(int axis, long pulse) {
    return pulse >= MIN_US[axis] && pulse <= MAX_US[axis];
}

bool speedInBounds(long speed) {
    return speed >= MIN_SPEED_US_PER_S && speed <= MAX_SPEED_US_PER_S;
}

void setSpeed(long requestedSpeed) {
    // Call only after validation. A new speed applies to any ongoing motion.
    speedUsPerSecond = requestedSpeed;
    const unsigned long now = millis();
    // Start a fresh interval so an old partially elapsed interval is not
    // charged at the new rate. Targets and fractional ramp positions remain.
    for (int axis = 0; axis < 2; ++axis) lastStepMs[axis] = now;
    Serial.print("Command speed set: ");
    Serial.print(speedUsPerSecond);
    Serial.println(" us/s");
}

void setTarget(int axis, long requestedUs) {
    // Call only after validation. Repeated targets must not discard fractional
    // progress; otherwise frequent requests could prevent very slow motion.
    if (targetUs[axis] == requestedUs) return;
    targetUs[axis] = static_cast<int>(requestedUs);
    // Retarget from the last output request, discarding <0.5 us of rounding
    // residue. Do not jump to the new endpoint or assume the shaft has arrived.
    rampMilliUs[axis] = currentUs[axis] * 1000L;
    acceptedMs[axis] = millis();
    lastStepMs[axis] = acceptedMs[axis];
    firstStepPending[axis] = currentUs[axis] != targetUs[axis];
    Serial.print(AXIS_NAME[axis]);
    Serial.print(" target accepted: ");
    Serial.print(targetUs[axis]);
    Serial.println(" us");
}

void stopMotion() {
    for (int axis = 0; axis < 2; ++axis) {
        targetUs[axis] = currentUs[axis];
        rampMilliUs[axis] = currentUs[axis] * 1000L;
        firstStepPending[axis] = false;
    }
    Serial.println("Stopped stepping. Servos still hold their last commands.");
    printStatus();
}

bool parseIntegers(char* text, long* values, int& count) {
    // Read at most three whitespace-separated decimal integers. strtol plus
    // explicit delimiter/overflow checks rejects decimals and trailing junk.
    count = 0;
    while (true) {
        while (isspace(static_cast<unsigned char>(*text))) ++text;
        if (*text == '\0') return true;
        if (count == 3) return false;
        char* end = nullptr;
        errno = 0;
        const long value = strtol(text, &end, 10);
        if (end == text || errno == ERANGE ||
            (*end != '\0' && !isspace(static_cast<unsigned char>(*end))))
            return false;
        values[count++] = value;
        text = end;
    }
}

void processLine(char* line) {
    while (isspace(static_cast<unsigned char>(*line))) ++line;
    size_t length = strlen(line);
    while (length > 0 && isspace(static_cast<unsigned char>(line[length - 1])))
        line[--length] = '\0';
    if (length == 0) return;
    if (strcmp(line, "?") == 0) {
        printStatus();
        return;
    }
    if (strcmp(line, "0") == 0) {
        // Reference return uses the currently selected speed.
        setTarget(TILT_CHANNEL, ZERO_US[TILT_CHANNEL]);
        setTarget(PAN_CHANNEL, ZERO_US[PAN_CHANNEL]);
        printStatus();
        return;
    }
    const char command = line[0];
    if ((command != 'p' && command != 't' && command != 's' && command != 'c') ||
        !isspace(static_cast<unsigned char>(line[1]))) {
        Serial.println("Use p N, t N, s RATE, c PAN TILT [RATE], x, 0, or ?.");
        return;
    }
    long values[3];
    int count = 0;
    if (!parseIntegers(line + 1, values, count)) {
        Serial.println("Rejected: use whole decimal numbers separated by spaces.");
        return;
    }
    if (command == 'c') {
        // Pair order is PAN then TILT, despite the array's channel order.
        // Validate the complete request before changing speed or EITHER axis.
        if ((count != 2 && count != 3) ||
            !pulseInBounds(PAN_CHANNEL, values[0]) ||
            !pulseInBounds(TILT_CHANNEL, values[1]) ||
            (count == 3 && !speedInBounds(values[2]))) {
            Serial.println("Rejected: c PAN_US TILT_US [SPEED_US_PER_S]; check bounds.");
            return;
        }
        if (count == 3 && values[2] != speedUsPerSecond) setSpeed(values[2]);
        setTarget(PAN_CHANNEL, values[0]);
        setTarget(TILT_CHANNEL, values[1]);
        printStatus();
        return;
    }
    if (count != 1) {
        Serial.println("Rejected: p, t and s each need exactly one integer.");
        return;
    }
    if (command == 's') {
        if (!speedInBounds(values[0])) {
            Serial.println("Rejected: speed must be 1..2500 us/s. Use x to stop.");
            return;
        }
        if (values[0] != speedUsPerSecond) setSpeed(values[0]);
    } else {
        const int axis = command == 'p' ? PAN_CHANNEL : TILT_CHANNEL;
        if (!pulseInBounds(axis, values[0])) {
            Serial.println("Rejected: outside this axis's configured pulse bounds.");
            return;
        }
        setTarget(axis, values[0]);
    }
    printStatus();
}

void handleSerial() {
    // A bounded parser lets motion continue while a line is incomplete.
    for (int count = 0; count < 64 && Serial.available() > 0; ++count) {
        const char c = Serial.read();
        // Preserve immediate stop: x cancels stepping before a newline and
        // discards all currently queued input so old targets cannot restart it.
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
    const long endpoint = targetUs[axis] * 1000L;
    if (rampMilliUs[axis] == endpoint) return;
    const unsigned long now = millis();
    if (now - lastStepMs[axis] < STEP_INTERVAL_MS) return;
    lastStepMs[axis] = now;
    // Advance one nominal interval only. After a stalled loop, do not issue
    // multiple missed steps or one large catch-up jump. Actual motion slows.
    // us/s * ms gives thousandths of a us, matching rampMilliUs's scale.
    const long maximumChange = speedUsPerSecond * STEP_INTERVAL_MS;
    const long difference = endpoint - rampMilliUs[axis];
    const long change = difference > maximumChange ? maximumChange
                      : difference < -maximumChange ? -maximumChange : difference;
    rampMilliUs[axis] += change; // Shorten the final step to stop at the endpoint.
    const int nextUs = static_cast<int>((rampMilliUs[axis] + 500L) / 1000L);
    if (nextUs != currentUs[axis]) {
        currentUs[axis] = nextUs;
        pwm.writeMicroseconds(axis, currentUs[axis]);
        if (firstStepPending[axis]) {
            firstStepPending[axis] = false;
            Serial.print(AXIS_NAME[axis]);
            Serial.print(" first output update after acceptance: ");
            Serial.print(millis() - acceptedMs[axis]);
            Serial.println(" ms");
        }
    }
    if (rampMilliUs[axis] == endpoint) {
        Serial.print(AXIS_NAME[axis]);
        Serial.print(" command ramp complete after ");
        Serial.print(millis() - acceptedMs[axis]);
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
    // Startup still directly commands references: initial angles are unknown.
    // Speed control applies to subsequent moves, not this first boot movement.
    for (int axis = 0; axis < 2; ++axis) {
        pwm.writeMicroseconds(axis, currentUs[axis]);
        lastStepMs[axis] = millis();
    }
    Serial.println("Manual coordinates and speed: 115200 baud, Newline.");
    Serial.println("p 1300 = pan | t 1350 = tilt | s 200 = command speed (us/s)");
    Serial.println("c 1300 1370 = pan/tilt pair | c 1300 1370 200 = pair plus speed");
    Serial.println("x = stop and hold | 0 = references at selected speed | ? = status");
    printStatus();
}

void loop() {
    handleSerial();
    updateAxis(TILT_CHANNEL);
    updateAxis(PAN_CHANNEL);
}
