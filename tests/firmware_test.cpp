// Host logic check only: no I2C bus, real library, ESP32 build or servo physics.
#include <cassert>
#include <iostream>
#include "Arduino.h"
#include "Wire.h"

unsigned long testClockMs = 0;
SerialStub Serial;
WireStub Wire;
#include "../firmware/turret_controller/TurretController/TurretController.ino"

// Advance a simulated clock rather than waiting for real wall-clock time.
void tick(unsigned long ms = 20) {
    testClockMs += ms;
    loop();
}

void send(const char* line) {
    while (*line) Serial.input.push_back(*line++);
    loop();
}

int main() {
    setup();
    assert(currentUs[0] == 1370 && currentUs[1] == 1270);

    // An off-grid target must finish exactly, with a shortened final step.
    send("p 1503\n");
    for (int i = 0; i < 5; ++i) tick();
    assert(currentUs[1] == 1503);
    int previous = 1270;
    for (size_t i = 2; i < pwm.writes.size(); ++i) {
        auto write = pwm.writes[i];
        assert(write.first == 1);
        assert(write.second - previous > 0 && write.second - previous <= 50);
        previous = write.second;
    }

    // A new target can reverse a move; x then prevents additional PWM writes.
    send("p 2000\n");
    tick();
    send("p 1000\n");
    tick();
    assert(currentUs[1] == 1503);
    send("x");
    auto count = pwm.writes.size();
    for (int i = 0; i < 30; ++i) tick();
    assert(pwm.writes.size() == count);

    // One invalid field rejects the entire managed pair.
    send("m 1400 9999\n");
    assert(targetUs[1] == 1503 && targetUs[0] == 1370);
    send("m 1400 1200junk\n");
    assert(!managedMode);
    send("m 1400\n");
    assert(!managedMode);
    send("m 1400 1200\n");
    assert(managedMode && targetUs[1] == 1400 && targetUs[0] == 1200);

    // After idle, the elapsed step interval permits an immediate first step.
    assert(currentUs[1] == 1453 && currentUs[0] == 1320);
    tick();
    assert(currentUs[1] == 1403 && currentUs[0] == 1270);
    tick(500);
    assert(!managedMode);
    assert(targetUs[1] == currentUs[1] && targetUs[0] == currentUs[0]);

    // Identical managed targets refresh the timer without restarting motion.
    send("m 2000 1200\n");
    for (int i = 0; i < 10; ++i) {
        tick(50);
        send("m 2000 1200\n");
    }
    assert(managedMode);

    // Rejected manual input must neither cancel nor refresh that timer.
    auto lastRefresh = lastManagedMs;
    send("p 2851\n");
    assert(managedMode && lastManagedMs == lastRefresh);
    tick(500);
    assert(!managedMode && targetUs[1] == currentUs[1]);

    // Overflow consumes the bad line, then parsing recovers at its newline.
    send("x");
    send("p 2851\n");
    assert(targetUs[1] == currentUs[1]);
    send("p 99999999999999999999999999999999999999999999999999999999\np 1270\n");
    for (int i = 0; i < 40; ++i) tick();
    assert(currentUs[1] == 1270);

    send("0\n");
    for (int i = 0; i < 30; ++i) tick();
    assert(currentUs[0] == 1370 && currentUs[1] == 1270);
    for (auto write : pwm.writes) {
        assert(write.second >= MIN_US[write.first]);
        assert(write.second <= MAX_US[write.first]);
    }
    std::cout << "PASS: ramp, retarget, stop, pair validation, watchdog, refresh, "
                 "bounds, overflow, references\n";
}
