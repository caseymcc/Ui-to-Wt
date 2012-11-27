include(FindPythonInterp)

find_program(UI_SCRIPT ui_to_wt.py
    PATHS "${CMAKE_MODULE_PATH}/scripts"
)

macro(ADD_UI_FILE_TO_LIBRARY ui_file)
	if(${UI_SCRIPT} STREQUAL "UI_SCRIPT-NOTFOUND")
		message("Could not find ui_to_wt python script used in preprocess ${ui_file}")
	endif(${UI_SCRIPT} STREQUAL "UI_SCRIPT-NOTFOUND")

    string(REGEX REPLACE "(.+)\\.ui$" "ui_\\1.h" h_file "${ui_file}")
    get_filename_component(h_file ${h_file} NAME)

	source_group("Form Files" FILES ${PROJECT_SOURCE_DIR}/${ui_file})
	source_group("Generated Files" FILES ${PROJECT_SOURCE_DIR}/${h_file})

	set(py_command "${PYTHON_EXECUTABLE} ${UI_SCRIPT} --header ${PROJECT_SOURCE_DIR}/${h_file} ${PROJECT_SOURCE_DIR}/${ui_file}")
    add_custom_command(
        OUTPUT ${PROJECT_SOURCE_DIR}/${h_file}
        DEPENDS ${PROJECT_SOURCE_DIR}/${ui_file} ${UI_SCRIPT}
        COMMAND ${PYTHON_EXECUTABLE} ${UI_SCRIPT} --header ${PROJECT_SOURCE_DIR}/${h_file} ${PROJECT_SOURCE_DIR}/${ui_file}
        COMMENT "Uic'ing ${ui_file} into ${h_file}"
    )
#	add_custom_target(ALL DEPENDS ${PROJECT_SOURCE_DIR}/${h_file})

    set(SET_SOURCE_FILE_PROPERTIES ${PROJECT_SOURCE_DIR}/${h_file} PROPERTIES GENERATED TRUE)
	set(UI_SOURCES ${UI_SOURCES} ${PROJECT_SOURCE_DIR}/${h_file})
	set(UI_SOURCES ${UI_SOURCES} ${PROJECT_SOURCE_DIR}/${ui_file})
endmacro(ADD_UI_FILE_TO_LIBRARY)

macro(ADD_UI_FILES_TO_LIBRARY ui_files)
    foreach(ui_file ${ui_files})
	ADD_UI_FILE_TO_LIBRARY(${ui_file})
    endforeach(ui_file ${ui_files})
endmacro(ADD_UI_FILES_TO_LIBRARY ui_files)