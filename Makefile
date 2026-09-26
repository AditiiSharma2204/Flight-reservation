CXX       = g++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Wpedantic -O2
TARGET    = flight

# On Windows, link the C++ runtime statically so the program doesn't pick up
# a mismatched libstdc++-6.dll (e.g. the one bundled with Git for Windows).
ifeq ($(OS),Windows_NT)
LDFLAGS  += -static
endif

all: $(TARGET)

$(TARGET): flight.cpp
	$(CXX) $(CXXFLAGS) $< -o $@ $(LDFLAGS)

run: $(TARGET)
	./$(TARGET)

test: $(TARGET)
	sh tests/smoke_test.sh ./$(TARGET)

clean:
	rm -f $(TARGET) $(TARGET).exe

.PHONY: all run test clean
