#pragma once
#include <vector>
#include <utility>
struct Adafruit_PWMServoDriver {
 std::vector<std::pair<int,int>> writes;
 bool begin() { return true; }
 void setPWMFreq(int) {}
 void writeMicroseconds(int channel,int value) { writes.emplace_back(channel,value); }
};
