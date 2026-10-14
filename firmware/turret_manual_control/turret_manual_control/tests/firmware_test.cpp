// Behavioral regression tests. These stubs record output requests; they do not
// simulate a servo, I2C, the ESP32 toolchain, or PCA9685 pulse quantization.
#include <cassert>
#include <iostream>
#include <limits>
#include <string>
#include "Arduino.h"
#include "Wire.h"
unsigned long testClockMs = 0;
SerialStub Serial;
WireStub Wire;
#include "../turret_manual_control.ino"

void resetFixture() {
    testClockMs = 0;
    Serial.input.clear(); Serial.output.clear(); pwm.writes.clear();
    speedUsPerSecond = DEFAULT_SPEED_US_PER_S;
    inputLength = 0; overflowed = false;
    for (int a = 0; a < 2; ++a) {
        currentUs[a] = targetUs[a] = ZERO_US[a];
        rampMilliUs[a] = ZERO_US[a] * 1000L;
        lastStepMs[a] = acceptedMs[a] = 0;
        firstStepPending[a] = false;
    }
    setup(); pwm.writes.clear(); Serial.output.clear();
}
void send(const std::string& bytes) {
    for (char c : bytes) Serial.input.push_back(c);
    while (Serial.available()) handleSerial();
}
void tick(unsigned long elapsed = 20) { testClockMs += elapsed; loop(); }
void ticks(int count) { for (int i = 0; i < count; ++i) tick(); }

int main() {
    int passed = 0;
    resetFixture(); send("p 1383\n"); tick(19);
    assert(currentUs[1] == 1270); tick(1);
    assert(currentUs[1] == 1320); ticks(2);
    assert(currentUs[1] == 1383 && currentUs[0] == 1370); ++passed;

    resetFixture(); send("c 1300 1350 200\n"); tick();
    assert(speedUsPerSecond == 200 && currentUs[1] == 1274 && currentUs[0] == 1366);
    ticks(7); assert(currentUs[1] == 1300 && currentUs[0] == 1350); ++passed;

    // An invalid pair cannot partially update the valid axis or the speed.
    resetFixture();
    for (const auto& cmd : {"c 1300 1511 200\n", "c 419 1350 200\n",
                           "c 1300 1350 0\n", "c 1300\n", "c 1300 1350 1 2\n"}) {
        send(cmd);
        assert(targetUs[0] == 1370 && targetUs[1] == 1270 && speedUsPerSecond == 2500);
    } ++passed;

    resetFixture(); send("s 500\np 1300\n"); tick();
    assert(currentUs[1] == 1280); ticks(2); assert(currentUs[1] == 1300); ++passed;

    resetFixture(); send("s 25\np 1272\n"); ticks(4);
    assert(currentUs[1] == 1272 && rampMilliUs[1] == 1272000); ++passed;

    // Very slow ramps retain sub-integer progress in either direction.
    resetFixture(); send("c 1271 1369 1\n"); ticks(50);
    assert(currentUs[1] == 1271 && currentUs[0] == 1369);
    assert(rampMilliUs[1] == 1271000 && rampMilliUs[0] == 1369000); ++passed;

    resetFixture(); send("s 25\np 1280\n"); tick();
    const long fraction = rampMilliUs[1]; tick(5); send("s 200\n");
    assert(rampMilliUs[1] == fraction && targetUs[1] == 1280);
    tick(19); assert(rampMilliUs[1] == fraction); tick(1);
    assert(rampMilliUs[1] == fraction + 4000); ++passed;

    resetFixture(); send("c 1271 1370 1\n");
    for (int i = 0; i < 50; ++i) { send("c 1271 1370 1\n"); tick(); }
    assert(currentUs[1] == 1271 && rampMilliUs[1] == 1271000); ++passed;

    resetFixture(); send("p 1500\n"); tick(); send("p 1280\n"); tick();
    assert(currentUs[1] == 1280 && targetUs[1] == 1280); ++passed;

    resetFixture(); send("c 1300 1350 25\n"); tick();
    send("xp 1500\nc 1500 1400\n");
    assert(targetUs[0] == currentUs[0] && targetUs[1] == currentUs[1]);
    const auto writeCount = pwm.writes.size(); ticks(100);
    assert(pwm.writes.size() == writeCount && !Serial.available()); ++passed;

    resetFixture(); send("c 1280 1360 100\n"); ticks(5); send("0\n"); ticks(5);
    assert(currentUs[0] == 1370 && currentUs[1] == 1270 && speedUsPerSecond == 100); ++passed;

    resetFixture(); send("p 1500\n"); send("t 135"); tick();
    assert(currentUs[1] == 1320 && targetUs[0] == 1370);
    send("0\n"); assert(targetUs[0] == 1350); ++passed;

    resetFixture(); send(std::string(90, '9') + "\np 1280\r\n"); tick();
    assert(currentUs[1] == 1280 && !overflowed);
    for (const auto& cmd : {"p 1280.5\n", "t 1360junk\n", "s -1\n", "s 2501\n",
                           "p 2851\n", "t 399\n", "p 999999999999999999999999\n"}) send(cmd);
    assert(targetUs[1] == 1280 && targetUs[0] == 1370 && speedUsPerSecond == 2500); ++passed;

    resetFixture(); send("s 200\np 1500\n"); tick(1000);
    assert(currentUs[1] == 1274); ++passed; // No catch-up burst.

    resetFixture(); testClockMs = std::numeric_limits<unsigned long>::max() - 10;
    send("p 1280\n"); tick(19); assert(currentUs[1] == 1270);
    tick(1); assert(currentUs[1] == 1280); ++passed; // Unsigned clock rollover.

    resetFixture(); send("c 2850 400 2500\n"); ticks(60);
    send("c 420 1510\n"); ticks(100);
    assert(currentUs[1] == 420 && currentUs[0] == 1510);
    for (const auto& output : pwm.writes) {
        assert(pulseInBounds(output.first, output.second));
    }
    ++passed;

    std::cout << passed << " behavior checks passed\n";
}
