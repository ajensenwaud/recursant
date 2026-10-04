cmake_minimum_required(VERSION 3.20)
project(recursant VERSION 0.1.0 LANGUAGES C)
set(CMAKE_C_STANDARD 17)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
option(RECURSANT_SANITIZERS "Enable address and undefined-behaviour checks" OFF)
option(RECURSANT_ENCODER "Local question encoder for context.prompt (needs ONNX Runtime headers; the library is loaded at run time)" OFF)

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
pkg_check_modules(INTERPRETER_DEPS IMPORTED_TARGET libcurl jansson)
if(INTERPRETER_DEPS_FOUND)
  add_library(recursant_interpreter STATIC core/src/context/interpreter.c)
  target_include_directories(recursant_interpreter PUBLIC core/include)
  target_link_libraries(recursant_interpreter PUBLIC Threads::Threads PkgConfig::INTERPRETER_DEPS)
  target_compile_options(recursant_interpreter PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_interpreter PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_interpreter PUBLIC -fsanitize=address,undefined)
  endif()
endif()
pkg_check_modules(ROUTER_DEPS IMPORTED_TARGET libmicrohttpd libcurl jansson libpcre2-8)
if(ROUTER_DEPS_FOUND)
  add_library(recursant_stream_tools STATIC core/src/context/stream_tools.c)
  target_include_directories(recursant_stream_tools PUBLIC core/include)
  target_link_libraries(recursant_stream_tools PUBLIC PkgConfig::ROUTER_DEPS)
  target_compile_options(recursant_stream_tools PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_stream_tools PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_stream_tools PUBLIC -fsanitize=address,undefined)
  endif()
  add_library(recursant_cost STATIC core/src/context/cost.c)
  target_include_directories(recursant_cost PUBLIC core/include)
  target_link_libraries(recursant_cost PUBLIC PkgConfig::ROUTER_DEPS)
  target_compile_options(recursant_cost PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_cost PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_cost PUBLIC -fsanitize=address,undefined)
  endif()
  add_library(recursant_signals STATIC core/src/context/signals.c)
  target_include_directories(recursant_signals PUBLIC core/include)
  target_link_libraries(recursant_signals PUBLIC PkgConfig::ROUTER_DEPS)
  target_compile_options(recursant_signals PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_signals PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_signals PUBLIC -fsanitize=address,undefined)
  endif()
  add_library(recursant_efficiency STATIC core/src/context/efficiency.c)
  target_include_directories(recursant_efficiency PUBLIC core/include)
  target_link_libraries(recursant_efficiency PUBLIC PkgConfig::ROUTER_DEPS m)
  target_compile_options(recursant_efficiency PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_efficiency PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_efficiency PUBLIC -fsanitize=address,undefined)
  endif()
  add_library(recursant_prompt STATIC core/src/context/prompt.c core/src/context/encoder.c core/src/context/wordpiece.c)
  target_include_directories(recursant_prompt PUBLIC core/include)
  target_link_libraries(recursant_prompt PUBLIC PkgConfig::ROUTER_DEPS m)
  if(RECURSANT_ENCODER)
    pkg_check_modules(ONNXRUNTIME REQUIRED libonnxruntime)
    target_compile_definitions(recursant_prompt PRIVATE RECURSANT_WITH_ENCODER)
    target_include_directories(recursant_prompt PRIVATE ${ONNXRUNTIME_INCLUDE_DIRS})
    target_link_libraries(recursant_prompt PUBLIC Threads::Threads ${CMAKE_DL_LIBS})
  endif()
  target_compile_options(recursant_prompt PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_prompt PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_prompt PUBLIC -fsanitize=address,undefined)
  endif()
  add_library(recursant_tools STATIC core/src/context/tool_boundary.c)
  target_include_directories(recursant_tools PUBLIC core/include)
  target_link_libraries(recursant_tools PUBLIC PkgConfig::ROUTER_DEPS)
  target_compile_options(recursant_tools PRIVATE -Wall -Wextra -Wpedantic -Werror)
  if(RECURSANT_SANITIZERS)
    target_compile_options(recursant_tools PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(recursant_tools PUBLIC -fsanitize=address,undefined)
  endif()
  add_executable(recursant core/src/http/router.c core/src/runtime.c core/src/compliance/classifier.c core/src/compliance/identifiers.c core/src/context/gateway_context.c core/src/context/response_observer.c core/src/context/judge.c core/src/providers/adapters.c core/src/providers/catalog.c core/src/net/netinfo.c core/src/cli/cli.c core/src/cli/configure.c)
  target_compile_definitions(recursant PRIVATE RECURSANT_VERSION="${PROJECT_VERSION}")
  target_link_libraries(recursant PRIVATE recursant_signals recursant_efficiency recursant_prompt recursant_cost recursant_stream_tools recursant_tools recursant_config recursant_selector recursant_context recursant_attempts recursant_interpreter Threads::Threads PkgConfig::ROUTER_DEPS)
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
  add_executable(test_attempts_capacity tests/unit/test_attempts_capacity.c)
  target_link_libraries(test_attempts_capacity PRIVATE recursant_attempts)
  target_compile_options(test_attempts_capacity PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
  add_test(NAME attempts_capacity COMMAND test_attempts_capacity)
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
  if(INTERPRETER_DEPS_FOUND)
    add_executable(test_interpreter_alloc tests/unit/test_interpreter_alloc.c)
    target_include_directories(test_interpreter_alloc PRIVATE core/include)
    target_link_libraries(test_interpreter_alloc PRIVATE Threads::Threads PkgConfig::INTERPRETER_DEPS)
    target_compile_options(test_interpreter_alloc PRIVATE -Wall -Wextra -Wpedantic -Werror)
    if(RECURSANT_SANITIZERS)
      target_compile_options(test_interpreter_alloc PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
      target_link_options(test_interpreter_alloc PRIVATE -fsanitize=address,undefined)
    endif()
    add_test(NAME interpreter_alloc COMMAND test_interpreter_alloc)
  endif()
  add_executable(test_identifiers tests/unit/test_identifiers.c core/src/compliance/identifiers.c)
  target_include_directories(test_identifiers PRIVATE core/include)
  target_compile_options(test_identifiers PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
  if(RECURSANT_SANITIZERS)
    target_compile_options(test_identifiers PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
    target_link_options(test_identifiers PRIVATE -fsanitize=address,undefined)
  endif()
  add_test(NAME identifiers_unit COMMAND test_identifiers)

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
    if(INTERPRETER_DEPS_FOUND)
      add_executable(test_interpreter tests/unit/test_interpreter.c)
      target_link_libraries(test_interpreter PRIVATE recursant_interpreter recursant_context)
      target_compile_options(test_interpreter PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME interpreter_loopback COMMAND ${Python3_EXECUTABLE}
        ${CMAKE_SOURCE_DIR}/tests/integration/test_interpreter.py -v)
      set_tests_properties(interpreter_loopback PROPERTIES TIMEOUT 45
        ENVIRONMENT "INTERPRETER_BIN=$<TARGET_FILE:test_interpreter>;PYTHONDONTWRITEBYTECODE=1")
    endif()
    if(ROUTER_DEPS_FOUND)
      add_executable(test_stream_tools tests/unit/test_stream_tools.c)
      target_link_libraries(test_stream_tools PRIVATE recursant_stream_tools)
      target_compile_options(test_stream_tools PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME stream_tools_unit COMMAND test_stream_tools)
      add_executable(test_cost tests/unit/test_cost.c)
      target_link_libraries(test_cost PRIVATE recursant_cost recursant_selector)
      target_compile_options(test_cost PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME cost_unit COMMAND test_cost)
      add_executable(test_signals tests/unit/test_signals.c)
      target_link_libraries(test_signals PRIVATE recursant_signals)
      target_compile_options(test_signals PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME signals_unit COMMAND test_signals)
      add_executable(test_efficiency tests/unit/test_efficiency.c)
      target_link_libraries(test_efficiency PRIVATE recursant_efficiency)
      target_compile_options(test_efficiency PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME efficiency_unit COMMAND test_efficiency)
      add_executable(test_prompt tests/unit/test_prompt.c)
      target_link_libraries(test_prompt PRIVATE recursant_prompt)
      target_compile_options(test_prompt PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME prompt_unit COMMAND test_prompt)
      # Encoder parity against the Hugging Face tokenizer and PyTorch. Needs the model
      # (bench/prompt/fetch_encoder.sh); skipped when RECURSANT_ENCODER_DIR is unset.
      set(RECURSANT_ENCODER_DIR "$ENV{RECURSANT_ENCODER_DIR}" CACHE PATH "Directory with bge-small-en-v1.5 model.onnx and vocab.txt")
      add_executable(test_wordpiece tests/unit/test_wordpiece.c)
      target_link_libraries(test_wordpiece PRIVATE recursant_prompt)
      target_compile_options(test_wordpiece PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME wordpiece_unit COMMAND test_wordpiece "${RECURSANT_ENCODER_DIR}/vocab.txt" ${CMAKE_SOURCE_DIR}/tests/fixtures/encoder-bge-small.jsonl)
      set_tests_properties(wordpiece_unit PROPERTIES SKIP_RETURN_CODE 77)
      if(RECURSANT_ENCODER)
        add_executable(test_encoder tests/unit/test_encoder.c)
        target_link_libraries(test_encoder PRIVATE recursant_prompt)
        target_compile_options(test_encoder PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
        add_test(NAME encoder_unit COMMAND test_encoder "${RECURSANT_ENCODER_DIR}/model.onnx" "${RECURSANT_ENCODER_DIR}/vocab.txt" ${CMAKE_SOURCE_DIR}/tests/fixtures/encoder-bge-small.jsonl)
        set_tests_properties(encoder_unit PROPERTIES SKIP_RETURN_CODE 77)
      endif()
      add_executable(test_tool_boundary tests/unit/test_tool_boundary.c)
      target_link_libraries(test_tool_boundary PRIVATE recursant_tools)
      target_compile_options(test_tool_boundary PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      add_test(NAME tool_boundary_unit COMMAND test_tool_boundary)
      add_test(NAME stream_tools_gateway COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_stream_tools_gateway.py -v)
      set_tests_properties(stream_tools_gateway PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME native_tools_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_native_tools.py -v)
      set_tests_properties(native_tools_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_executable(test_response_observer tests/unit/test_response_observer.c core/src/context/response_observer.c)
      target_include_directories(test_response_observer PRIVATE core/include)
      target_link_libraries(test_response_observer PRIVATE recursant_stream_tools PkgConfig::ROUTER_DEPS)
      target_compile_options(test_response_observer PRIVATE -Wall -Wextra -Wpedantic -Werror -UNDEBUG)
      target_compile_definitions(test_response_observer PRIVATE RC_FIXTURE_DIR="${CMAKE_SOURCE_DIR}/tests/fixtures")
      if(RECURSANT_SANITIZERS)
        target_compile_options(test_response_observer PRIVATE -fsanitize=address,undefined -fno-omit-frame-pointer)
        target_link_options(test_response_observer PRIVATE -fsanitize=address,undefined)
      endif()
      add_test(NAME response_observer_unit COMMAND test_response_observer)
      add_test(NAME gateway_context_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_context.py -v)
      set_tests_properties(gateway_context_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_cost_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_cost.py -v)
      set_tests_properties(gateway_cost_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_signals_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_signals.py -v)
      set_tests_properties(gateway_signals_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_sessions_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_sessions.py -v)
      set_tests_properties(gateway_sessions_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_judge_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_judge.py -v)
      set_tests_properties(gateway_judge_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_efficiency_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_efficiency.py -v)
      set_tests_properties(gateway_efficiency_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_prompt_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_prompt.py -v)
      set_tests_properties(gateway_prompt_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_compliance_memo_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_compliance_memo.py -v)
      set_tests_properties(gateway_compliance_memo_integration PROPERTIES TIMEOUT 120
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME native_profile_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_native_profile.py -v)
      set_tests_properties(native_profile_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_capacity_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_capacity.py -v)
      set_tests_properties(gateway_capacity_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_health_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_health.py -v)
      set_tests_properties(gateway_health_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_context_fit_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_context_fit.py -v)
      set_tests_properties(gateway_context_fit_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_reasoning_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_reasoning.py -v)
      set_tests_properties(gateway_reasoning_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_housekeeping_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_housekeeping.py -v)
      set_tests_properties(gateway_housekeeping_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_budgets_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_budgets.py -v)
      set_tests_properties(gateway_budgets_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_headers_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_headers.py -v)
      set_tests_properties(gateway_headers_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME gateway_shadow_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_gateway_shadow.py -v)
      set_tests_properties(gateway_shadow_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
      add_test(NAME compliance_identifiers_integration COMMAND ${Python3_EXECUTABLE}
        -m unittest discover -s ${CMAKE_SOURCE_DIR}/tests/integration -p test_compliance_identifiers.py -v)
      set_tests_properties(compliance_identifiers_integration PROPERTIES TIMEOUT 180
        ENVIRONMENT "RECURSANT_BIN=$<TARGET_FILE:recursant>;PYTHONDONTWRITEBYTECODE=1")
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
      add_test(NAME cli_integration
               COMMAND ${Python3_EXECUTABLE} -m unittest discover -s
                       ${CMAKE_SOURCE_DIR}/tests/integration -p test_cli.py -v)
      set_tests_properties(cli_integration PROPERTIES
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
