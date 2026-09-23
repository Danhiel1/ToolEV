# 🎬 ToolEV — Turn Videos into English & IELTS Lessons

<p align="center">
  <strong>Biến mọi video trên mạng thành bài học tiếng Anh & bộ đề luyện thi IELTS Listening hoàn chỉnh.</strong><br>
  Tự động bóc tách phụ đề (YouTube Caption / Whisper AI Local) • Tự động tạo bài tập trắc nghiệm & điền từ • Luyện nghe chép chính tả (Dictation).
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/Engine-faster--whisper-FF6F00?style=flat" alt="Whisper" />
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-4D4D4D?style=flat" alt="Platform" />
  <img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License" />
</p>

---

## 🌟 Giới thiệu

**ToolEV** là công cụ học tiếng Anh thông minh chạy cục bộ (100% Local) trên máy tính của bạn. Bạn chỉ cần cung cấp một đường link video YouTube (hoặc video bất kỳ), ToolEV sẽ tự động:

1. **Bóc tách nội dung** (lấy phụ đề gốc hoặc dùng mô hình AI Whisper nhận diện giọng nói).
2. **Biên soạn đề thi IELTS Listening** chuẩn form thi thật (Trắc nghiệm, Điền từ, Trả lời ngắn) kèm mốc thời gian phát âm thanh và lời giải thích.
3. **Mở trình phát bài học** trực quan trên trình duyệt để bạn vừa xem video, vừa làm bài tập chấm điểm tức thì hoặc luyện nghe chép chính tả (Dictation).

---

## ✨ Tính năng nổi bật

- ⚡ **Khởi động 1-Click trên Windows**: Chỉ cần nhấp đúp file `run.bat`, hệ thống tự thiết lập môi trường và mở ngay trình duyệt.
- 🔗 **Dán link trực tiếp trên Web UI**: Không cần gõ lệnh dòng lệnh, chỉ cần dán link YouTube vào ô nhập trên giao diện web và bấm *Tạo bài học*.
- 🎙️ **Bóc tách Transcript thông minh**:
  - **Nhánh siêu tốc**: Tự động lấy phụ đề gốc YouTube, không tốn tài nguyên CPU, phát video mượt mà qua YouTube IFrame (tiết kiệm ổ cứng).
  - **Nhánh AI Offline**: Tự động chuyển sang mô hình **Whisper local** (`faster-whisper`) để nghe và nhận diện giọng nói khi video không có phụ đề sẵn.
- 📝 **Tự động sinh bộ đề IELTS Listening chuẩn**:
  - **Multiple Choice** (Trắc nghiệm 3–4 lựa chọn).
  - **Sentence / Note Completion** (Điền từ vào chỗ trống kèm quy định số từ: *"CHỈ MỘT TỪ"*, *"KHÔNG QUÁ HAI TỪ"*...).
  - **Short Answer** (Trả lời ngắn theo nội dung video).
  - Tự động cắt đúng đoạn âm thanh nghe câu trả lời (`start` → `end`), trích dẫn câu thoại giải thích chi tiết.
- 🎧 **Trình luyện nghe Dictation chuyên sâu**:
  - Luyện nghe gõ từng câu, tua lặp đoạn khó, gợi ý ký tự.
  - Tự động tắt phụ đề native của YouTube để tránh lộ đáp án khi luyện nghe.
- 🔒 **Bảo mật & Cá nhân**: Toàn bộ dữ liệu bài học lưu trữ trực tiếp trên máy của bạn (`output/`).

---

## 🚀 Hướng dẫn cài đặt & Chạy nhanh

### 🪟 Dành cho Windows:

#### Cách 1: Tải file tự bung 1-Click (Khuyên dùng - Không cần cài Python)
1. Tải file **`ToolEV_Setup.exe`** từ thư mục `dist/` (hoặc [Releases](https://github.com/Danhiel1/ToolEV/releases)).
2. Nhấp đúp vào **`ToolEV_Setup.exe`** và bấm **Bắt đầu (Extract)**.
3. Ứng dụng sẽ tự động bung mã nguồn, Python 3.11 Portable, toàn bộ thư viện AI (Whisper, yt-dlp, ctranslate2) và FFmpeg.
4. Tự động tạo biểu tượng **ToolEV** ngoài màn hình Desktop và khởi chạy ngầm êm ái ở khay hệ thống (System Tray) mà không hiện cửa sổ dòng lệnh đen.

#### Cách 2: Chạy trực tiếp từ mã nguồn
1. Tải mã nguồn về máy: Bấm nút **Code** > **Download ZIP** (hoặc `git clone https://github.com/Danhiel1/ToolEV`).
2. Nhấp đúp vào file **`run.bat`**.
3. Giao diện bài học sẽ xuất hiện tại: 👉 **`http://localhost:8000/all-video.html`**

---

### 🍎 Dành cho macOS / Linux:

1. Mở Terminal tại thư mục dự án:
   ```bash
   # Cài đặt công cụ media (nếu chưa có)
   # macOS: brew install ffmpeg yt-dlp
   # Ubuntu/Debian: sudo apt install ffmpeg && pip install yt-dlp

   # Tạo môi trường ảo Python và cài thư viện
   python3 -m venv scripts/.venv
   source scripts/.venv/bin/activate
   pip install -r scripts/requirements.txt
   ```

2. Khởi động server:
   ```bash
   python3 server.py 8000
   ```

3. Mở trình duyệt truy cập: **`http://localhost:8000/all-video.html`**

---

## 📖 Cách sử dụng

1. Trên thanh công cụ trên cùng của trang web, bấm vào nút màu đỏ **`+ Thêm video`**.
2. Dán link video YouTube bạn muốn học (ví dụ: `https://www.youtube.com/watch?v=...`).
3. Chọn ngôn ngữ (*Tiếng Anh* / *Tiếng Việt*) và bấm **`Tạo bài học ngay`**.
4. Theo dõi thanh tiến độ thời gian thực (Phân tích link ➔ Lấy phụ đề ➔ Soạn câu hỏi IELTS).
5. Khi hoàn tất, bấm **`Mở bài học vừa tạo`** để bắt đầu luyện nghe và làm bài tập trắc nghiệm!

---

## 📂 Cấu trúc thư mục

```text
toolev/
├── all-video.html          # Giao diện Web (Thư viện bài học, IELTS Player, Dictation)
├── server.py               # Máy chủ local phục vụ media & API xử lý video
├── run.bat                 # Trình khởi chạy 1-Click tự động cho Windows
├── output/                 # Thư mục chứa các bài học đã tạo (<slug>/...)
│   └── <slug>/
│       ├── ielts_listening.json   # Bộ câu hỏi IELTS Listening kèm đáp án & mốc thời gian
│       ├── thumb.jpg              # Ảnh thumbnail của bài học
│       ├── video.mp4              # File video/audio local (nếu có)
│       └── parts/                 # Dữ liệu transcript chi tiết từng phân đoạn
└── scripts/
    ├── requirements.txt    # Danh sách thư viện Python (faster-whisper, yt-dlp, requests)
    ├── pipeline.py         # Pipeline điều phối tải media và bóc tách
    ├── generate_ielts.py   # Trình sinh câu hỏi và bài tập IELTS Listening
    ├── transcribe.py       # Engine bóc transcript bằng Whisper local AI
    └── yt_transcript.py    # Bộ xử lý và chuyển đổi phụ đề YouTube gốc
```

---

## ⚙️ Yêu cầu hệ thống

- **Python**: Phiên bản `3.10` trở lên (khi cài đặt nhớ tích chọn *"Add Python to PATH"*).
- **FFmpeg** *(Tùy chọn cho nhánh video offline)*:
  - Windows: Mở Terminal/CMD gõ `winget install Gyan.FFmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

---

## 🛡️ Miễn trừ trách nhiệm (Disclaimer)

Công cụ này được xây dựng **chỉ phục vụ cho mục đích học tập và nghiên cứu cá nhân** (tải và dịch phụ đề nhằm rèn luyện kỹ năng nghe hiểu ngoại ngữ). Người dùng tự chịu trách nhiệm tuân thủ Điều khoản dịch vụ (Terms of Service) của nền tảng nguồn và pháp luật hiện hành về bản quyền. Nghiêm cấm sử dụng công cụ cho mục đích thương mại, reup hoặc phân phối lại nội dung trái phép.

---

## 👤 Tác giả & Hỗ trợ (Author & Contact)
- **Tác giả / Developer**: [Danhiel1](https://github.com/Danhiel1)
- **GitHub Repository**: [https://github.com/Danhiel1/ToolEV](https://github.com/Danhiel1/ToolEV)
- **Email hỗ trợ**: [nguyenminhhieu.stu@gmail.com](mailto:nguyenminhhieu.stu@gmail.com)

---

## 📄 License

Dự án được phân phối theo giấy phép [Apache License 2.0](LICENSE) — Bản quyền © 2026 Danhiel1 (ToolEV).
