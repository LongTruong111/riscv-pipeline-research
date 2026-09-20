REPO_ROOT := $(abspath ../../..)

SIM ?= verilator
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = $(REPO_ROOT)/tests/week4_counter.sv

TOPLEVEL = week4_counter
MODULE = test_throughput

export PYTHONPATH := $(REPO_ROOT)/research/week5/preflight:$(REPO_ROOT)/tests:$(PYTHONPATH)

include $(shell cocotb-config --makefiles)/Makefile.sim
