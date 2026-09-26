CXX       = g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Wpedantic -O2
TARGET    = flight

all: $(TARGET)

$(TARGET): flight.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

run: $(TARGET)
	./$(TARGET)

test: $(TARGET)
	sh tests/smoke_test.sh ./$(TARGET)

clean:
	rm -f $(TARGET) $(TARGET).exe

.PHONY: all run test clean
