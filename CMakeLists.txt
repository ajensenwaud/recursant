cmake_minimum_required(VERSION 3.20)
project(recursant VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
option(RECURSANT_SANITIZERS "Enable address and undefined-behaviour checks" OFF)

add_library(recursant_selector STATIC core/src/context/selector.c)
target_include_directories(recursant_selector PUBLIC core/include)
target_compile_options(recursant_selector PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_library(recursant_context STATIC core/src/context/context.c)
add_library(recursant_attempts STATIC core/src/context/attempts.c)
target_include_directories(recursant_attempts PUBLIC core/include)
target_compile_options(recursant_attempts PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(recursant_attempts PUBLIC recursant_auth)
set_target_properties(recursant_attempts PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(recursant_context PUBLIC core/include)
target_compile_options(recursant_context PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_library(recursant_policy STATIC core/src/compliance/egress.c)
target_include_directories(recursant_policy PUBLIC core/include)
target_compile_options(recursant_policy PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_library(recursant_config STATIC core/src/config/config.c)
target_include_directories(recursant_config PUBLIC core/include)
target_compile_options(recursant_config PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_library(recursant_auth STATIC core/src/auth/auth.c)
target_include_directories(recursant_auth PUBLIC core/include)
target_compile_options(recursant_auth PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(recursant_auth PUBLIC recursant_config)
set_target_properties(recursant_auth recursant_config PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_library(recursant_admission STATIC core/src/http/admission.c)
target_include_directories(recursant_admission PUBLIC core/include)
target_compile_options(recursant_admission PRIVATE -Wall -Wextra -Wpedantic -Werror)
target_link_libraries(recursant_admission PUBLIC recursant_auth)

add_executable(recursant-validate core/src/admin/validate.c)
target_link_libraries(recursant-validate PRIVATE recursant_config)
target_compile_options(recursant-validate PRIVATE -Wall -Wextra -Wpedantic -Werror)

find_package(Threads REQUIRED)
find_package(PkgConfig QUIET)
pkg_check_modules(ROUTER_DEPS IMPORTED_TARGET libmicrohttpd libcurl jansson libpcre2-8)
if(ROUTER_DEPS_FOUND)
  add_executable(recursant core/src/http/router.c core/src/runtime.c core/src/compliance/classifier.c)
  target_link_libraries(recursant PRIVATE recursant_config Threads::Threads PkgConfig::ROUTER_DEPS)
  target_compile_options(recursant PRIVATE -Wall -Wextra -Wpedantic -Werror)
else()
  message(STATUS "router dependencies (libmicrohttpd/libcurl/jansson/pcre2) not found: "
                 "recursant binary and its integration tests are skipped")
endif()
add_executable(recursant-tracer core/src/http/tracer.c)
target_link_libraries(recursant-tracer PRIVATE Threads::Threads recursant_admission)
target_compile_options(recursant-tracer PRIVATE -Wall -Wextra -Wpedantic -Werror)

if(RECURSANT_SANITIZERS)
  target_compile_options(recursant_selector PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant_selector PUBLIC -fsanitize=address,undefined)
  target_compile_options(recursant_attempts PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant_attempts PUBLIC -fsanitize=address,undefined)
  target_compile_options(recursant_context PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant_context PUBLIC -fsanitize=address,undefined)
  target_compile_options(recursant_policy PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant_policy PUBLIC -fsanitize=address,undefined)
  target_compile_options(recursant_config PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant_config PUBLIC -fsanitize=address,undefined)
  target_compile_options(recursant-tracer PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(recursant-tracer PRIVATE -fsanitize=address,undefined)
endif()

include(CTest)
if(BUILD_TESTING)
  add_executable(test_selector tests/unit/test_selector.c)
  target_link_libraries(test_selector PRIVATE recursant_selector)
  target_compile_options(test_selector PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_test(NAME selector_unit COMMAND test_selector)

  add_executable(test_attempts tests/unit/test_attempts.c)
  target_link_libraries(test_attempts PRIVATE recursant_attempts)
  target_compile_options(test_attempts PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
  add_test(NAME attempts_unit COMMAND test_attempts)
  add_executable(test_attempts_internal tests/unit/test_attempts_internal.c)
  target_link_libraries(test_attempts_internal PRIVATE recursant_auth)
  target_compile_options(test_attempts_internal PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
  if(RECURSANT_SANITIZERS)
    target_compile_options(test_attempts_internal PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(test_attempts_internal PRIVATE -fsanitize=address,undefined)
  endif()
  add_test(NAME attempts_overflow COMMAND test_attempts_internal)
  add_library(attempt_probe SHARED tests/fixtures/attempt_probe.c)
  target_link_libraries(attempt_probe PRIVATE recursant_attempts)
  target_compile_options(attempt_probe PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_executable(test_context tests/unit/test_context.c)
  target_link_libraries(test_context PRIVATE recursant_context)
  target_compile_options(test_context PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_test(NAME context_unit COMMAND test_context)

  add_executable(test_egress tests/unit/test_egress.c)
  target_link_libraries(test_egress PRIVATE recursant_policy)
  target_compile_options(test_egress PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_test(NAME egress_policy COMMAND test_egress)

  add_executable(test_config tests/unit/test_config.c)
  target_link_libraries(test_config PRIVATE recursant_config)
  target_compile_options(test_config PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_test(NAME config_strict COMMAND test_config)

  add_executable(test_admission tests/unit/test_admission.c)
  target_link_libraries(test_admission PRIVATE recursant_admission)
  target_compile_options(test_admission PRIVATE -Wall -Wextra -Wpedantic -Werror)
  add_test(NAME admission_unit COMMAND test_admission)

  find_package(Python3 COMPONENTS Interpreter)
  if(Python3_FOUND)
    if(ROUTER_DEPS_FOUND)
      add_test(NAME hermes_observer
               COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                       ${CMAKE_SOURCE_DIR}/deploy/hermes -p "test_*.py" -v)
      set_tests_properties(hermes_observer PROPERTIES
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME compliance_integration
               COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                       ${CMAKE_SOURCE_DIR}/tests/integration -p test_compliance.py -v)
      set_tests_properties(compliance_integration PROPERTIES
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1"
        TIMEOUT 180)
      add_test(NAME router_integration
               COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                       ${CMAKE_SOURCE_DIR}/tests/integration -p "test_router*.py" -v)
      set_tests_properties(router_integration PROPERTIES
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1"
        TIMEOUT 180)
    endif()
    add_test(NAME transport_integration
             COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                     ${CMAKE_SOURCE_DIR}/tests/integration -p test_transport.py -v)
    set_tests_properties(transport_integration PROPERTIES
      ENVIRONMENT "RECURSANT_TRACER_BIN=$<TARGET_FILE:recursant-tracer>;PYTHONDONTWRITEBYTECODE=1")
    add_test(NAME admission_integration
             COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                     ${CMAKE_SOURCE_DIR}/tests/integration -p test_admission.py -v)
    set_tests_properties(admission_integration PROPERTIES
      ENVIRONMENT "RECURSANT_TRACER_BIN=$<TARGET_FILE:recursant-tracer>;PYTHONDONTWRITEBYTECODE=1")
    add_test(NAME trajectory_reference
             COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                     ${CMAKE_SOURCE_DIR}/tests -p test_trajectory_reference.py -v)
    set_tests_properties(trajectory_reference PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")
    add_test(NAME accounting
             COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                     ${CMAKE_SOURCE_DIR}/tests -p test_accounting.py -v)
    set_tests_properties(accounting PROPERTIES
      WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
      ENVIRONMENT "PYTHONDONTWRITEBYTECODE=1")
  endif()
endif()
