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
### 🪟 Dành cho Windows (Khuyên dùng):
1. **Tải mã nguồn về máy**:
   - Bấm nút **Code** > **Download ZIP** (hoặc `git clone` repository này về máy).
2. **Chạy ứng dụng**:
   - Nhấp đúp (Double-click) vào file **`run.bat`**.
   - *File sẽ tự động kiểm tra Python, cài đặt thư viện cần thiết, khởi động máy chủ và tự động mở trình duyệt.*
3. **Giao diện bài học sẽ xuất hiện tại**:
   👉 **`http://localhost:8000/all-video.html`**
