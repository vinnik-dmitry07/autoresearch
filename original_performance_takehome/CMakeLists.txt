cmake_minimum_required(VERSION 3.20)
project(vliw_machine CXX)

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

add_library(vliw_engine STATIC
    src/machine.cpp
    src/profiler.cpp
)
target_include_directories(vliw_engine PUBLIC include)
target_compile_features(vliw_engine PUBLIC cxx_std_23)

add_library(vliw_machine SHARED
    src/c_api.cpp
)
target_link_libraries(vliw_machine PRIVATE vliw_engine)
target_include_directories(vliw_machine PUBLIC include)
target_compile_definitions(vliw_machine PRIVATE VLIW_EXPORTS)
target_compile_features(vliw_machine PUBLIC cxx_std_23)

enable_testing()

add_executable(engine_tests tests/engine_tests.cpp)
target_link_libraries(engine_tests PRIVATE vliw_engine)
target_include_directories(engine_tests PRIVATE tests)
add_test(NAME engine_tests COMMAND engine_tests)

add_executable(engine_integration_tests tests/engine_integration_tests.cpp)
target_link_libraries(engine_integration_tests PRIVATE vliw_engine)
target_include_directories(engine_integration_tests PRIVATE tests)
add_test(NAME engine_integration COMMAND engine_integration_tests)

add_executable(profiler_tests tests/profiler_tests.cpp)
target_link_libraries(profiler_tests PRIVATE vliw_engine)
target_include_directories(profiler_tests PRIVATE tests)
add_test(NAME profiler_tests COMMAND profiler_tests)

find_program(VLIW_PYTHON NAMES python python3)
if(VLIW_PYTHON)
    add_test(
        NAME engine_py
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_engine.py
    )
    set_tests_properties(engine_py PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
    add_test(
        NAME profiler_metrics_py
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_profiler_metrics.py
    )
    set_tests_properties(profiler_metrics_py PROPERTIES WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})
    add_test(
        NAME profiler_integration_py
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_profiler_integration.py
    )
    set_tests_properties(profiler_integration_py PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        TIMEOUT 180
    )
    add_test(
        NAME engine_integration_py
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_engine_integration.py
    )
    set_tests_properties(engine_integration_py PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        TIMEOUT 180
    )
    add_test(
        NAME engine_e2e
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_engine_e2e.py
    )
    set_tests_properties(engine_e2e PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        TIMEOUT 300
    )
    add_test(
        NAME profiler_e2e
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/tests/test_profiler_e2e.py
    )
    set_tests_properties(profiler_e2e PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        TIMEOUT 300
    )
    add_test(
        NAME pipeline_bench
        COMMAND ${VLIW_PYTHON} -u ${CMAKE_SOURCE_DIR}/scripts/bench_pipeline_regression.py --check --cli
    )
    set_tests_properties(pipeline_bench PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        TIMEOUT 90
    )
endif()

add_executable(asymptotics tests/bench_asymptotics.cpp)
target_link_libraries(asymptotics PRIVATE vliw_engine)
target_include_directories(asymptotics PRIVATE tests)
