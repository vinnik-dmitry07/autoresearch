# Fails if the agent-editable no-memory strategy uses forbidden constructs:
# persistent state, I/O, clocks, threading, or randomness. Run via:
#   cmake -DSRC=<path> -P check_forbidden.cmake
if(NOT DEFINED SRC)
    message(FATAL_ERROR "SRC not set")
endif()

file(READ "${SRC}" content)

set(patterns
    "static"
    "fstream"
    "ofstream"
    "ifstream"
    "iostream"
    "random_device"
    "mt19937"
    "chrono"
    "thread"
    "filesystem"
    "std::rand"
)

set(found "")
foreach(p ${patterns})
    string(FIND "${content}" "${p}" idx)
    if(NOT idx EQUAL -1)
        list(APPEND found "${p}")
    endif()
endforeach()

if(found)
    message(FATAL_ERROR "Forbidden symbols in ${SRC}: ${found}")
endif()

message(STATUS "check_forbidden: OK (${SRC})")
