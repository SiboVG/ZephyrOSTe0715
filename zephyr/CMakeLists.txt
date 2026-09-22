# SPDX-License-Identifier: Apache-2.0

if(CONFIG_LIBPARAM)
  set(LIBPARAM_DIR ${WEST_TOPDIR}/modules/lib/libparam)
  if(NOT EXISTS ${LIBPARAM_DIR}/src/param/param.c)
    message(FATAL_ERROR "libparam not found at ${LIBPARAM_DIR}; run west update")
  endif()

  # The default libparam csh/2.10 Meson source set, as in fprime-csp-libparam
  zephyr_library_named(libparam)
  zephyr_library_sources(
    ${LIBPARAM_DIR}/src/param/list/param_list.c
    ${LIBPARAM_DIR}/src/param/param_client.c
    ${LIBPARAM_DIR}/src/param/param_serializer.c
    ${LIBPARAM_DIR}/src/param/param_server.c
    ${LIBPARAM_DIR}/src/param/param_string.c
    ${LIBPARAM_DIR}/src/param/param_queue.c
    ${LIBPARAM_DIR}/src/param/param_wildcard.c
    ${LIBPARAM_DIR}/src/param/param.c
    ${LIBPARAM_DIR}/src/mpack/mpack.c
    ${LIBPARAM_DIR}/src/vmem/vmem_client.c
    ${LIBPARAM_DIR}/src/vmem/vmem_crc32.c
    ${LIBPARAM_DIR}/src/vmem/vmem_server.c
    ${LIBPARAM_DIR}/src/vmem/vmem.c
    ${LIBPARAM_DIR}/src/vmem/vmem_block.c
    ${LIBPARAM_DIR}/src/objstore/objstore.c
  )
  zephyr_include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}/libparam
    ${LIBPARAM_DIR}/include
    ${LIBPARAM_DIR}
  )
  zephyr_library_include_directories(
    ${LIBPARAM_DIR}/src
    ${LIBPARAM_DIR}/src/param/list
  )
  # strlcpy() and friends: libbsd on Linux, BSD extensions of picolibc here
  zephyr_library_compile_definitions(_DEFAULT_SOURCE)
  # Harmless in this third-party code, but very noisy with Zephyr's flags
  zephyr_library_compile_options(-Wno-pointer-arith -Wno-double-promotion)
  zephyr_library_link_libraries(libcsp)
endif()
