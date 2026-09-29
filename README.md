# Xương - video - game

Bộ tool Python tự chơi game và xuất video dọc 1080×1920 (mặc định 50 giây) để đăng TikTok TEE và YouTube Shorts.
Kế hoạch đầy đủ: [docs/ke-hoach.md](docs/ke-hoach.md).

| Game | File | Hook mặc định |
| --- | --- | --- |
| **Kim Cương TEE** (ưu tiên) | [kim-cuong/gem_bot.py](kim-cuong/gem_bot.py) | Bom nổ liên hoàn tới đâu? |
| **Nông Trại Của TEE** | [nong-trai/farm_bot.py](nong-trai/farm_bot.py) | 50 giây làm giàu từ 40 xu |
| **Vẽ Tranh TEE** | [ve-tranh/draw_bot.py](ve-tranh/draw_bot.py) | không chữ, không tiếng — để ghép và lồng nhạc |

## Cấu trúc thư mục

```
xuong-video-game/
├── app.py                   # giao diện quản lý (python app.py)
├── ui/index.html            # trang web của giao diện
├── kim-cuong/gem_bot.py     # game kim cương: ghép 3, bom, siêu bom, mưa bom
├── nong-trai/farm_bot.py    # game nông trại: gieo, thu hoạch, mở đất, mưa, chợ phiên
├── ve-tranh/draw_bot.py     # vẽ tranh: bút chì phác từng nét → cọ tô mảng → tô chi tiết
├── assets/
│   ├── fonts/Baloo2.ttf     # font (giấy phép OFL, xem OFL.txt)
│   ├── kim-cuong/           # đặt PNG tự làm vào đây để thay hình vẽ sẵn (giai đoạn 2)
│   ├── nong-trai/
│   └── ve-tranh/tranh/      # ảnh nguồn cho game vẽ tranh (không đưa lên Git)
├── data/
│   ├── hooks.txt            # danh sách câu hook để thử
│   └── so-lieu.csv          # bảng số liệu test thị trường (giai đoạn 3)
├── docs/ke-hoach.md         # kế hoạch dự án
└── output/                  # video và ảnh xem thử (không đưa lên Git)
```

## Cài đặt

1. Python 3.10 trở lên.
2. ffmpeg trong PATH — kiểm tra bằng `ffmpeg -version`.
   Windows: tải bản build tại gyan.dev, giải nén, thêm thư mục `bin` vào PATH.
3. Thư viện:
   ```
   pip install -r requirements.txt
   ```

## Giao diện quản lý (khuyên dùng)

```
python app.py          # hoặc bấm đúp mo-giao-dien.bat
```

Trình duyệt tự mở `http://127.0.0.1:8765`. Tắt bằng Ctrl+C trong cửa sổ dòng lệnh.

| Trang | Dùng để |
| --- | --- |
| **Tạo video** | chọn game, seed, hook, câu hỏi, độ dài → xem thử 4 khung hình → render; render hàng loạt nhiều seed, tự xoay vòng hook |
| **Dò seed** | mô phỏng nhanh hàng chục ván (không render), xếp theo điểm / nổ liên hoàn / số xu để chọn ván kịch tính |
| **Hàng đợi** | theo dõi tiến độ, hủy; mặc định render 2 video cùng lúc (`python app.py --workers 3` để tăng) |
| **Thư viện** | xem video, lọc theo game / đã đăng, đánh dấu đã đăng, thêm dòng số liệu, xóa |
| **Số liệu** | sửa bảng `data/so-lieu.csv` ngay trên web, tự tổng hợp công thức nào có tỉ lệ xem hết cao nhất |
| **Câu hook** | sửa `data/hooks.txt` |

Video render từ giao diện được lưu vào `output/<ngày>/`, kèm file `.json` (seed, hook, tóm tắt ván) và ảnh bìa `.jpg`.

## Gửi sang máy khác (Windows / Mac M1) bằng file zip

```
python dong_goi.py                 # → dist/Xuong-video-game_<ngày>.zip (bỏ output/, .git)
python dong_goi.py --kem-output    # kèm video đã render
```

Máy nhận không cần cài Python hay ffmpeg: giải nén rồi bấm đúp **CHAY-WINDOWS.bat** hoặc
**CHAY-MAC.command**. Lần đầu cần Internet: [uv](https://docs.astral.sh/uv/) tự tải Python 3.12,
thư viện và ffmpeg (gói `imageio-ffmpeg`) vào `.runtime/` trong thư mục, khoảng 200 MB, không
đụng gì tới máy. Chi tiết cho người nhận (kể cả cách vượt Gatekeeper trên Mac):
[HUONG-DAN-CHAY.txt](HUONG-DAN-CHAY.txt).

Đừng nén bằng "Send to → Compressed folder" của Windows: zip đó mất quyền chạy của
`CHAY-MAC.command`.

## Chạy bằng dòng lệnh

Chạy từ bất kỳ đâu, kết quả luôn nằm trong `output/`.

```
cd kim-cuong
python gem_bot.py --preview 5,20,36                 # xem nhanh vài ảnh (vài giây)
python gem_bot.py                                   # xuất video 50 giây (~35 giây trên máy thử)
python gem_bot.py --seed 25 --out v2.mp4            # ván khác
python gem_bot.py --hook "Ván này được bao nhiêu điểm?" --duration 30

cd ../nong-trai
python farm_bot.py --preview 5,20,36
python farm_bot.py --seed 11
```

Tùy chọn dòng lệnh (cả 2 game):

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--seed N` | số ván; mỗi seed ra một ván khác, cùng seed luôn ra cùng ván |
| `--out tên.mp4` | tên file; chỉ ghi tên thì lưu vào `output/` |
| `--preview 5,20,36` | chỉ xuất ảnh PNG ở các giây này, không render video |
| `--hook "..."` | câu hook đầu video |
| `--question "..."` | câu hỏi cuối video (dùng `\n` để xuống dòng trong CONFIG) |
| `--duration 30` | độ dài video (giây) |

Khi thử nghiệm mà render chậm thì dùng `--duration 20`, xuất thật thì bỏ đi.

## Chỉnh game (phần `CONFIG` đầu mỗi file)

**Kim cương** — nhịp như người chơi: `think_min` / `think_max` (giây nghĩ trước mỗi nước), `touch_time` (chạm giữ), `swipe_time` (gạt), `skill` (độ giỏi 0–1), `decoy_chance` (lưỡng lự), `speed` (nhân tốc độ cả ván). Đổi nhanh không cần sửa file: `python gem_bot.py --duration 180 --set think_max=2 --set skill=0.5`.

**Kim cương (luật)** — `bomb_spawn` (tỉ lệ bom rơi xuống), `super_spawn`, `rain_every` (mỗi mấy giây có mưa bom, 0 = tắt),
`rain_count`, `end_card` (số giây hiện câu hỏi cuối), `music_volume`, `crf`.

**Nông trại** — `start_money`, `start_plots`, `plot_price`, `plot_price_grow`, `rain_every`, `market_every`
và bảng `CROPS` (giá hạt, giá bán, thời gian lớn của từng loại cây).

Mỗi lần chạy, dòng đầu in ra tóm tắt ván (điểm, số vụ nổ, combo…). Dùng nó để chọn seed kịch tính trước khi render.

## Template giao diện game kim cương (9 mẫu)

3 giao diện × 3 bộ icon, định nghĩa trong [kim-cuong/gem_templates.py](kim-cuong/gem_templates.py):

| Giao diện (`theme`) | Font | | Bộ icon (`items`) | 6 loại viên |
| --- | --- | --- | --- | --- |
| `dem` — Đêm tím | Baloo 2 | | `kim-cuong` — Kim cương | 6 viên đá quý |
| `keo` — Kẹo ngọt | Paytone One | | `do-an` — Đồ ăn | bánh mì, bánh bao, đùi gà, trứng ốp la, donut, pizza |
| `neon` — Neon | Chakra Petch | | `trai-cay` — Trái cây | dưa hấu, cam, nho, chuối, dâu, táo xanh |

Icon đều vẽ bằng code (không dùng emoji/ảnh của bên thứ ba). Chọn trên giao diện (trang Tạo video) hoặc:
`python gem_bot.py --theme keo --items do-an`. Khi render hàng loạt có thể xoay vòng cả 9 template.

Video mặc định **không có tiếng** (`"audio": False` trong CONFIG); bật lại bằng `--set audio=1`.

## Thay hình bằng asset tự làm (giai đoạn 2)

Không cần sửa code — chỉ cần đặt file PNG vuông, nền trong suốt:

- `assets/kim-cuong/`: `gem_0.png` … `gem_5.png` (đỏ, vàng, xanh lá, xanh dương, tím, xanh ngọc), `bomb.png`, `super_bomb.png`
- `assets/nong-trai/`: `soil.png`, `farmer.png`, `crop_<loại>_<giai đoạn>.png`
  (loại 0–6 theo thứ tự trong `CROPS`, giai đoạn 0–8, 8 là chín)

Thiếu file nào thì game tự vẽ hình đó như cũ.

## Kho clip nền cho video đọc truyện (`tao_kho_nen.py`)

Game làm **nền động** cho video truyện audio dài 1–2 tiếng (video-ticktok › project_5).
Bên đó không render game lúc dựng (một tập 2 tiếng sẽ tốn thêm ~90 phút CPU) mà bốc clip
làm sẵn trong kho ra nối lại. Ghép như vậy chỉ chậm hơn ảnh tĩnh ~18%.

**Cách dễ nhất: trang "Kho nền" trên giao diện** (menu dưới cùng, mục *Cho video truyện*):
① chọn thư mục kho (nút 📂 mở hộp thoại của Windows) → ② bấm **Làm N clip nền** → ③ xem lưới
clip, bấm để xem, xoá clip xấu. Ô ① có sẵn dòng `P5_GAME_NEN_DIR=…` để dán sang `.env` của
video-ticktok. Trang này **tách hẳn** khỏi "Tạo video" / "Render hàng loạt" (hai nút đó làm Shorts
để đăng, có hook + end card — không dùng làm nền được). Web chỉ gọi `tao_kho_nen.py` bên dưới, nên
chạy tay hay bấm nút đều ra cùng một kho. Thư mục đã chọn lưu ở `data/kho-nen.json`.

Hoặc chạy dòng lệnh:

```
python tao_kho_nen.py --so 9 --xem        # xem kế hoạch trước (không render)
python tao_kho_nen.py --so 9              # làm 9 clip × 3 phút, đủ 9 kiểu giao diện
python tao_kho_nen.py --so 9 --vong 10    # 10 vòng × 9 = 90 clip, chạy một lần (trên web: ô "Số vòng lặp")
python tao_kho_nen.py --liet-ke           # kho có bao nhiêu clip / phút không trùng
```

- Kết quả ở `kho-nen/kim-cuong/` (không đưa lên Git). **Bên dùng kho chỉ đọc `manifest.json`**,
  không tự quét `*.mp4`: clip đang render dở mang tên `_dang_…mp4`.
- Chạy lại là **làm tiếp**, không làm lại: seed đã có trong kho thì không dùng nữa, kiểu giao
  diện nào ít clip nhất thì được làm trước. Ctrl+C lúc nào cũng được, clip đã xong vẫn còn.
- Mỗi clip khác nhau ở 4 lớp: 9 template · seed · nhịp chơi (tốc độ, độ giỏi, mưa bom
  thưa/dày/tắt) · **chọn lọc** (mô phỏng 40 seed rồi render ván kịch tính nhất, `--do`).
- Clip chạy ở **chế độ nền** (`gem_bot.py --nen`): không hook (chỗ đó để trống cho tên truyện),
  không end card, đồng hồ không nháy đỏ, không chớp sáng, băng "MƯA BOM" thu nhỏ.
  `--khong-hud` bỏ luôn bảng TOP/Level/điểm.
- Mỗi clip 3 phút tốn ~2 phút CPU. Kho càng lớn thì video dài càng ít lặp: tập 2 tiếng
  cần 40 clip mới không lặp lại clip nào.

## Game vẽ tranh (`ve-tranh/draw_bot.py`)

Tự vẽ lại một bức tranh trên tờ giấy dán băng keo, khung dọc 1080×1920, **không tiếng, không chữ**.
Nét bút và vùng màu được tách tự động từ ảnh (cần `scipy`).

1. **Phác nét**: bút chì đi từng nét như tay người, đặt bút chậm, giữa nét nhanh tay, cuối nét
   chậm lại rồi nhấc bút, cứ 25–45 nét lại dừng ngắm. Nét dài (dáng chính) trước, nét ngắn sau.
2. **Tô mảng**: cọ tô từng vùng màu liền nhau, vùng rộng trước.
3. **Tô chi tiết**: cọ quét lần hai lộ dần tranh thật, nét chì mờ đi.
4. Giữ tranh hoàn chỉnh 7 giây.

Mặc định **độ dài tự nhiên** theo nhịp tay người: tranh càng nhiều nét càng dài (thường 8–15 phút,
render mất khoảng 1,5 lần độ dài video).

**Trên giao diện** (Tạo video › Vẽ Tranh TEE, hoặc mở thẳng `http://127.0.0.1:8765/?game=ve-tranh`):
kéo thả ảnh vào khung Tranh → chọn tranh → nhập % cắt watermark (nhớ riêng từng tranh) → Xem thử
(4 khung: đang phác · phác xong · tô mảng · hoàn thành, kèm độ dài video) → Render.
Tick “Chỉ render 30 giây đầu” để duyệt nhịp nhanh. Render hàng loạt: tất cả tranh × danh sách seed.

Dòng lệnh:

```
cd ve-tranh
python draw_bot.py --anh tranh.jpg --cat 4.5,6            # cắt 4,5% trên, 6% dưới (bỏ watermark)
python draw_bot.py --anh tranh.jpg --chi-render 30        # chỉ xuất 30 giây đầu
python draw_bot.py --anh tranh.jpg --set toc_do=1.5       # nhanh hơn 1,5 lần
python draw_bot.py --anh tranh.jpg --duration 180         # ép vừa 3 phút
python draw_bot.py --seed 3                               # không ghi --anh: ảnh thứ (seed) trong assets/ve-tranh/tranh/
```

Tham số trong `CONFIG`: `toc_do` (nhân tốc độ cả video), `toc_do_but` (điểm ảnh/giây của bút chì),
`toc_do_co` (của cọ), `net_dai`, `so_mau`, `hold`. Tranh rõ viền, nền đơn giản thì nét sạch hơn.
Chỉ dùng tranh bạn có quyền dùng (tự tạo bằng AI…), không lấy tranh có watermark của người khác để đăng.

## Âm thanh và bản quyền

- Tiếng động và nhạc nền hiện đều **tự tổng hợp bằng code**, không có bản quyền của ai.
- Khi đăng, nên tắt nhạc (`music_volume: 0`) rồi chọn nhạc trong thư viện của TikTok / YouTube Audio Library.
- Không dùng tên, logo, hình của Candy Crush, Bejeweled, Tetris, Nông Trại Vui Vẻ.
- Mô tả kênh nên ghi rõ đây là mô phỏng game tự chơi. Nếu dùng asset/giọng đọc AI, bật nhãn nội dung AI.

## Tiến độ

**Giai đoạn 1 — Cài đặt và chạy thử**
- [x] Tạo thư mục dự án với `kim-cuong/` và `nong-trai/`
- [x] Viết `gem_bot.py` và `farm_bot.py`, font Baloo 2
- [x] Render thử video kim cương và nông trại (50 giây, 1080×1920, có tiếng)
- [ ] Đưa code lên repo Git riêng (đã `git init`, chưa commit / push)

**Giai đoạn 2 — đã chuẩn bị sẵn**
- [x] Tùy chọn `--hook`, `--question`, `--duration`
- [x] Tự đọc asset PNG nếu có
- [ ] Bộ asset AI, logo + màu thương hiệu TEE, tiếng động thư viện, 10 video đạt chuẩn

Các giai đoạn tiếp theo: xem [docs/ke-hoach.md](docs/ke-hoach.md).
