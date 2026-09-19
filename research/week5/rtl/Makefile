THIS_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(THIS_DIR)/../../..)

SIM ?= verilator
TOPLEVEL_LANG = verilog

VERILOG_SOURCES = \
	$(REPO_ROOT)/design/RegPack.sv \
	$(filter-out $(REPO_ROOT)/design/RegPack.sv,$(sort $(wildcard $(REPO_ROOT)/design/*.sv))) \
	$(sort $(wildcard $(REPO_ROOT)/design/*.v)) \
	$(THIS_DIR)/execution_stream_tb.sv

TOPLEVEL = execution_stream_tb
MODULE = test_execution_stream_live

# Keep generated simulator files under the already-ignored sim_build tree.
SIM_BUILD := $(REPO_ROOT)/sim_build/week5_execution_stream

export PYTHONPATH := $(THIS_DIR):$(REPO_ROOT):$(PYTHONPATH)

ifeq ($(SIM),verilator)
COMPILE_ARGS += -Wno-fatal
endif

include $(shell cocotb-config --makefiles)/Makefile.sim
