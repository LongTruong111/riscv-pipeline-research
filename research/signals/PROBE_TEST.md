# PROBE_TEST

| Probe | Hiện tượng | Signal | Period | Kết quả |
|---|---|---|---|---|
| P1 | RAW — forwarding bật | forunit output | mỗi posedge clk | ✅ 0→01; Program B: x3=25 khớp golden |
| P2 | RAW — forward cả 2 ngõ ALU | FAmux.y, FBmux.y | posedge | ✅ add x3,x2,x2 → 30 = 15+15 |
| P3 | Reset giữ PC | pcreg.q, reset | 0–20ns | ✅ |
| P4 | PC tăng đều | pcreg.q | posedge 5–315ns | ✅ |

Ghi chú: baseline chưa có lệnh load/branch → probe load-use và branch sẽ bổ sung khi có test tương ứng.
