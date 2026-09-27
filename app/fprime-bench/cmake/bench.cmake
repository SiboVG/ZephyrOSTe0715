# SPDX-License-Identifier: Apache-2.0
#
# bench_add_revision_header(LIBRARY_PATH): generate bench_revision.h for the Zephyr app
# target at every build (see revision.cmake).
function(bench_add_revision_header library_path)
    set(header "${CMAKE_CURRENT_BINARY_DIR}/bench_revision/bench_revision.h")
    add_custom_target(bench_revision
        COMMAND "${CMAKE_COMMAND}" "-DOUT=${header}" "-DBENCH=${CMAKE_CURRENT_LIST_DIR}"
                "-DLIBRARY=${library_path}" -P "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/revision.cmake"
        BYPRODUCTS "${header}"
        COMMENT "Recording bench and library revisions")
    add_dependencies(app bench_revision)
    target_include_directories(app PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/bench_revision")
endfunction()
