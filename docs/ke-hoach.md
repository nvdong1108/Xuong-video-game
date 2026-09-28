# Kế hoạch dự án: Video game tự chơi TEE

Sep 27, 2026 · @Someone

## Tổng quan

Mục tiêu: một bộ tool Python tự chơi game và xuất video dọc 50 giây, để đăng TikTok và YouTube Shorts hằng ngày mà gần như không cần làm tay.

- **Đã có:** 2 bản mẫu chạy được: `gem_bot.py` (game kim cương, bom, mưa bom) và `farm_bot.py` (nông trại).
- **Ưu tiên:** game kim cương, vì người xem hiểu luật trong 2 giây đầu. Nông trại để dành, test sau.
- **Nơi đăng:** kênh TikTok TEE và YouTube Shorts.

&#91;embedded content: lộ trình · 5 giai đoạn, 4 cổng kiểm tra\]

Mỗi giai đoạn chỉ bắt đầu khi qua cổng phía trước. Thời gian là đề xuất, bạn có thể kéo dài tùy sức.

## Giai đoạn 1: Cài đặt và chạy thử (tuần 1)

Kết quả cần đạt: tự render lại được 2 video mẫu trên máy của bạn, và hiểu chỗ nào trong code để chỉnh.

1. Tạo thư mục dự án, ví dụ `tee-game-video/`, gồm 2 thư mục con `kim-cuong/` và `nong-trai/`.
2. Cài Python 3.10 trở lên và ffmpeg (Windows: tải bản build, thêm vào PATH; kiểm tra bằng `ffmpeg -version`).
3. Cài thư viện: `pip install pillow numpy`.
4. Chép `gem_bot.py`, `farm_bot.py` và font `Baloo2.ttf` vào đúng thư mục.
5. Chạy thử:
   - `python gem_bot.py --preview 5,20,36` để xem nhanh vài ảnh.
   - `python gem_bot.py` để xuất video 50 giây (mất khoảng 1–2 phút).
   - `python gem_bot.py --seed 25 --out v2.mp4` để ra một ván khác.
6. Đưa code lên một repo Git riêng để lưu lịch sử thay đổi.
7. Đọc phần `CONFIG` đầu file và thử đổi: câu hook, tên game, câu hỏi cuối, `bomb_spawn`, `rain_every`.

Nếu render chậm, giảm `duration` xuống 20 giây khi thử, rồi trả về 50 khi xuất thật.

## Giai đoạn 2: Nâng cấp hình ảnh và âm thanh (tuần 2–3)

Kết quả cần đạt: 10 video đạt chuẩn đăng, nhìn và nghe khác rõ so với bản mẫu.

**Hình ảnh**

1. Tạo bộ asset bằng AI cùng một phong cách: 6 viên kim cương, bom, siêu bom, nền. File PNG nền trong suốt, kích thước vuông.
2. Sửa hàm `gem_sprite()` và `bomb_sprite()` để đọc ảnh PNG thay vì tự vẽ. Logic game giữ nguyên.
3. Thêm logo TEE góc trên và màu thương hiệu riêng cho kênh.

**Âm thanh**

1. Thay tiếng tự tổng hợp bằng thư viện tiếng miễn phí bản quyền (nổ, vỡ kính, xu, còi báo).
2. Nhạc nền: dùng nhạc trong thư viện được phép của TikTok hoặc YouTube Audio Library, không chèn nhạc có bản quyền vào file.

**Nội dung video**

1. Viết 10 câu hook khác nhau, ví dụ "Bom nổ liên hoàn tới đâu?", "Ván này được bao nhiêu điểm?".
2. Thêm tùy chọn `--hook` để đổi câu hook từ dòng lệnh.
3. Thử 3 độ dài: 30, 50 và 60 giây.
4. Xuất 10 video với 10 seed khác nhau, xem lại trên điện thoại trước khi đăng.

## Giai đoạn 3: Test thị trường (tuần 3–5)

Kết quả cần đạt: biết chắc game nào, hook nào, độ dài nào giữ người xem tốt nhất, trước khi bỏ công tự động hóa.

1. Đăng 1–2 video mỗi ngày trong 14 ngày, giờ đăng cố định.
2. Mỗi lần chỉ đổi một yếu tố (hook, độ dài, hoặc game) để biết cái nào tạo ra khác biệt.
3. Xen 3–4 video nông trại để so với kim cương.
4. Sau 48 giờ, ghi số liệu từ TikTok Analytics / YouTube Studio vào bảng dưới.
5. Trả lời bình luận trong giờ đầu, ghim bình luận đoán điểm hay nhất.
6. Cuối tuần 5: chọn công thức thắng (game + kiểu hook + độ dài) để làm hàng loạt.

Chỉ số quan trọng nhất là tỉ lệ xem hết và thời gian xem trung bình; lượt xem sẽ tăng theo hai số này.

| Ngày đăng | Game | Hook | Độ dài (giây) | Lượt xem 48h | Xem hết (%) | TB xem (giây) | Bình luận | Follow mới |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | Kim cương | Bom nổ liên hoàn tới đâu? | 50 |  |  |  |  |  |
|  | Kim cương |  |  |  |  |  |  |  |
|  | Nông trại | 50 giây làm giàu từ 40 xu | 50 |  |  |  |  |  |

## Giai đoạn 4: Tự động hóa hàng loạt (tuần 6–7)

Kết quả cần đạt: mỗi tối bấm một lệnh, sáng hôm sau có sẵn video đủ dùng cho cả tuần.

1. Viết script `batch_render.py`: đọc danh sách seed + hook từ file CSV, render lần lượt, lưu vào `output/<ngày>/`.
2. Chạy nhiều tiến trình song song (mỗi nhân CPU một video) để rút ngắn thời gian.
3. Tự sinh kèm mỗi video: tiêu đề, mô tả, hashtag, ảnh bìa (khung hình đẹp nhất, ví dụ lúc nổ cực đại).
4. Lọc tự động: bỏ ván có quá ít bom nổ hoặc điểm thấp, chỉ giữ ván kịch tính.
5. YouTube Shorts: đăng và hẹn giờ qua YouTube Data API.
6. TikTok: hẹn giờ bằng công cụ lên lịch có sẵn của TikTok (an toàn hơn bot tự đăng).
7. Ghi log mỗi video (seed, hook, ngày đăng) để nối với bảng số liệu ở giai đoạn 3.

## Giai đoạn 5: Mở rộng (từ tuần 8)

Kết quả cần đạt: nhiều dòng video cùng chạy tự động, mỗi dòng có điểm khác biệt riêng.

1. **Game mới dùng lại khung sẵn có:** xếp gạch rơi, xếp bi theo màu, đào vàng. Mỗi game chỉ cần viết lại phần luật và bot; phần render, âm thanh, xuất video giữ nguyên.
2. **Tách phần chung ra thư viện riêng** (`engine/`: render, âm thanh, ffmpeg, hiệu ứng) để mỗi game mới nhanh hơn.
3. **Ghép audio truyện TEE:** dùng game tự chơi làm nền, phủ giọng đọc TTS và phụ đề một đoạn truyện. Kiểu video này giữ người xem lâu và kéo người về web truyện.
4. **Series theo trend:** mùa lễ (Trung thu, Tết, Noel) đổi màu, đổi viên kim cương thành bánh, lồng đèn.
5. **Tương tác:** video "bình luận seed, mình chạy ván của bạn" — dùng số người xem gửi làm seed.

## Lưu ý chính sách và bản quyền

- **Nội dung lặp lại:** YouTube và TikTok hạn chế kiếm tiền với video sản xuất hàng loạt, gần giống nhau. Mỗi video cần khác thật: hook, sự kiện, nhạc, chủ đề — không chỉ đổi seed.
- **Tên và hình game gốc:** không dùng tên, logo, hình của Candy Crush, Bejeweled, Tetris, Nông Trại Vui Vẻ. Giữ tên riêng (Kim Cương TEE, Nông Trại Của TEE) và asset tự làm.
- **Nhạc:** chỉ dùng nhạc có giấy phép hoặc thư viện của nền tảng.
- **Nhãn AI:** nếu dùng asset hoặc giọng đọc do AI tạo, bật nhãn nội dung AI khi đăng nếu nền tảng yêu cầu.
- **Hiệu ứng chớp sáng:** giữ chớp nhẹ và ngắn như bản hiện tại, tránh gây khó chịu cho người xem nhạy cảm ánh sáng.
- **Minh bạch:** mô tả kênh nên ghi rõ đây là mô phỏng game tự chơi, tránh người xem tưởng là game có thật để tải về.

## Checklist tiến độ

**Giai đoạn 1**

- [ ] Cài Python, ffmpeg, pillow, numpy
- [ ] Render lại video kim cương trên máy mình
- [ ] Render lại video nông trại trên máy mình
- [ ] Đưa code lên Git

**Giai đoạn 2**

- [ ] Bộ asset AI: 6 viên, bom, siêu bom, nền
- [ ] Code đọc asset PNG
- [ ] Logo và màu thương hiệu TEE
- [ ] Tiếng động miễn phí bản quyền
- [ ] 10 câu hook + tùy chọn `--hook`
- [ ] 10 video đạt chuẩn

**Giai đoạn 3**

- [ ] Đăng đều 14 ngày
- [ ] Điền bảng số liệu sau mỗi 48 giờ
- [ ] Chọn công thức thắng

**Giai đoạn 4**

- [ ] `batch_render.py` đọc CSV, render song song
- [ ] Tự sinh tiêu đề, hashtag, ảnh bìa
- [ ] Lọc ván kém kịch tính
- [ ] Hẹn giờ đăng YouTube qua API, TikTok qua công cụ lên lịch

**Giai đoạn 5**

- [ ] Tách thư viện `engine/` dùng chung
- [ ] Game thứ ba
- [ ] Video game nền + audio truyện TEE
- [ ] Series theo mùa lễ
