THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(THIS_DIR)/../../..)

SIM ?= verilator
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = \
	$(REPO_ROOT)/design/RegPack.sv \
	$(filter-out $(REPO_ROOT)/design/RegPack.sv,$(sort $(wildcard $(REPO_ROOT)/design/*.sv))) \
	$(sort $(wildcard $(REPO_ROOT)/design/*.v)) \
	$(REPO_ROOT)/research/week5/rtl/execution_stream_tb.sv

TOPLEVEL = execution_stream_tb
MODULE = test_retire_monitor_live

SIM_BUILD := $(REPO_ROOT)/sim_build/week7_retire_monitor

export PYTHONPATH := $(THIS_DIR):$(REPO_ROOT):$(PYTHONPATH)

ifeq ($(SIM),verilator)
COMPILE_ARGS += -Wno-fatal
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
