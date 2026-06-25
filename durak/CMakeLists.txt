cmake_minimum_required(VERSION 3.20)
project(durak CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

if(MSVC)
    add_compile_options(/O2 /EHsc /W4 /permissive-)
else()
    add_compile_options(-O3 -Wall -Wextra)
endif()

add_library(durak_engine STATIC
    src/engine.cpp
    src/strategies.cpp
    src/strategy_random_legal.cpp
    src/strategy_basic_nomem.cpp
    src/strategy_heuristic.cpp
    src/strategy_heuristic_mem.cpp
    src/strategy_mem.cpp
)
target_include_directories(durak_engine PUBLIC include)
target_compile_features(durak_engine PUBLIC cxx_std_23)

add_library(play_ui STATIC
    src/play_ui.cpp
    src/play_session.cpp
)
target_link_libraries(play_ui PUBLIC durak_engine)

add_executable(simulate src/simulate.cpp)
target_link_libraries(simulate PRIVATE durak_engine)

add_executable(play src/play.cpp)
target_link_libraries(play PRIVATE durak_engine)

add_executable(web_server src/web_server.cpp)
target_compile_definitions(web_server PRIVATE "DURAK_WEB_DIR=\"${CMAKE_CURRENT_SOURCE_DIR}/web\"")
target_include_directories(web_server PRIVATE third_party)
target_link_libraries(web_server PRIVATE play_ui durak_engine)
if(WIN32)
    target_link_libraries(web_server PRIVATE ws2_32)
endif()

enable_testing()

add_executable(engine_tests tests/engine_tests.cpp)
target_link_libraries(engine_tests PRIVATE durak_engine)
add_test(NAME engine_tests COMMAND engine_tests)

add_executable(simulation_tests tests/simulation_tests.cpp)
target_link_libraries(simulation_tests PRIVATE durak_engine)
add_test(NAME simulation_tests COMMAND simulation_tests)

add_test(NAME forbidden_check
    COMMAND ${CMAKE_COMMAND}
        -DSRC=${CMAKE_CURRENT_SOURCE_DIR}/src/strategy_heuristic.cpp
        -P ${CMAKE_CURRENT_SOURCE_DIR}/cmake/check_forbidden.cmake
)
