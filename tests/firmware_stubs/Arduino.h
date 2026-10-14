#pragma once
#include <deque>
#include <string>
#include <sstream>
extern unsigned long testClockMs;
inline unsigned long millis() { return testClockMs; }
inline void delay(unsigned long value) { testClockMs += value; }
struct SerialStub {
 std::deque<char> input;
 std::string output;
 void begin(int) {}
 int available() { return static_cast<int>(input.size()); }
 char read() { const char c=input.front(); input.pop_front(); return c; }
 template<typename T> void print(T value) { std::ostringstream s; s<<value;output+=s.str(); }
 template<typename T> void println(T value) { print(value);output+='\n'; }
};
extern SerialStub Serial;
