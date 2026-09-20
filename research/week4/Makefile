REPO_ROOT := $(abspath ../..)

SIM ?= icarus
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(REPO_ROOT)/tests/week4_counter.sv

TOPLEVEL = week4_counter
MODULE = test_week4_timing_race

export PYTHONPATH := $(REPO_ROOT)/tests:$(PYTHONPATH)

ifeq ($(SIM),icarus)
COMPILE_ARGS += -g2012
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
