#!/usr/bin/env python3
"""
ToolEV Automated Standalone & SFX Packager
Builds a 100% self-extracting, portable executable (dist/ToolEV_Setup.exe)
containing Python runtime, all AI libraries (faster-whisper, ctranslate2, yt-dlp),
ffmpeg binaries, and web interface.
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BUILD_DIR = BASE_DIR / "build"
STAGING_DIR = BUILD_DIR / "staging"
DIST_DIR = BASE_DIR / "dist"
CSC_PATH = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")

# Ensure UTF-8 output
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print(f"📦 [ToolEV Packager] {msg}", flush=True)


def clean_dir(d: Path):
    if d.exists():
        log(f"Đang dọn dẹp thư mục: {d.name}...")
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)


def copy_python_runtime(staging_runtime: Path):
    """Sao chép Python Portable runtime độc lập từ base Python và venv site-packages"""
    base_python = Path(sys.base_prefix)
    log(f"Đang chuẩn bị Python Portable từ: {base_python}...")
    staging_runtime.mkdir(parents=True, exist_ok=True)

    # 1. Copy core DLLs and EXEs
    for fname in ["python.exe", "pythonw.exe", "python311.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll"]:
        src = base_python / fname
        if src.exists():
            shutil.copy2(src, staging_runtime / fname)

    # 2. Copy DLLs folder
    src_dlls = base_python / "DLLs"
    if src_dlls.is_dir():
        log("Sao chép thư mục DLLs của Python...")
        shutil.copytree(src_dlls, staging_runtime / "DLLs", dirs_exist_ok=True)

    # 3. Copy standard Lib (excluding bloat)
    src_lib = base_python / "Lib"
    dst_lib = staging_runtime / "Lib"
    dst_lib.mkdir(parents=True, exist_ok=True)
    log("Sao chép thư viện chuẩn Python (Lib)...")

    skip_dirs = {"test", "idlelib", "turtledemo", "tkinter", "ensurepip", "__pycache__", "site-packages"}
    for item in src_lib.iterdir():
        if item.name in skip_dirs:
            continue
        dst_item = dst_lib / item.name
        if item.is_dir():
            shutil.copytree(item, dst_item, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, dst_item)

    # 4. Copy site-packages from .venv
    venv_site = BASE_DIR / "scripts" / ".venv" / "Lib" / "site-packages"
    dst_site = dst_lib / "site-packages"
    dst_site.mkdir(parents=True, exist_ok=True)

    log(f"Sao chép các thư viện AI từ venv: {venv_site}...")
    skip_packages = {"pip", "setuptools", "wheel", "_distutils_hack", "pkg_resources"}
    for item in venv_site.iterdir():
        if item.name.startswith(("pip-", "setuptools-", "wheel-", "pip", "setuptools", "wheel", "_distutils")):
            continue
        if item.name in skip_packages:
            continue
        dst_item = dst_site / item.name
        if item.is_dir():
            shutil.copytree(item, dst_item, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, dst_item)

    # Loại bỏ file pth lỗi nếu có
    pth_file = dst_site / "distutils-precedence.pth"
    if pth_file.exists():
        pth_file.unlink()

    log("Python Portable runtime đã được cấu hình xong.")


def copy_project_files(staging: Path):
    """Sao chép mã nguồn, giao diện web, công cụ ffmpeg và dữ liệu mặc định"""
    log("Sao chép mã nguồn và giao diện web ToolEV...")

    # 1. Core web & server
    shutil.copy2(BASE_DIR / "server.py", staging / "server.py")
    shutil.copy2(BASE_DIR / "all-video.html", staging / "all-video.html")
    shutil.copy2(BASE_DIR / "run.bat", staging / "run.bat")
    if (BASE_DIR / "stop.bat").exists():
        shutil.copy2(BASE_DIR / "stop.bat", staging / "stop.bat")
    if (BASE_DIR / "README.md").exists():
        shutil.copy2(BASE_DIR / "README.md", staging / "README.md")
    if (BASE_DIR / "LICENSE").exists():
        shutil.copy2(BASE_DIR / "LICENSE", staging / "LICENSE")

    # 2. Scripts folder (clean)
    staging_scripts = staging / "scripts"
    staging_scripts.mkdir(parents=True, exist_ok=True)
    for sfile in (BASE_DIR / "scripts").iterdir():
        if sfile.name in (".venv", "__pycache__"):
            continue
        if sfile.is_file():
            shutil.copy2(sfile, staging_scripts / sfile.name)

    # 3. Bin folder (ffmpeg/ffprobe)
    bin_dir = BASE_DIR / "bin"
    if bin_dir.is_dir():
        log("Sao chép ffmpeg và ffprobe từ bin/...")
        shutil.copytree(bin_dir, staging / "bin", dirs_exist_ok=True)

    # 4. Output folder (default caches only)
    staging_output = staging / "output"
    staging_output.mkdir(parents=True, exist_ok=True)
    for fname in ["dict_cache.json", "saved_vocab.json"]:
        src = BASE_DIR / "output" / fname
        if src.exists():
            shutil.copy2(src, staging_output / fname)

    # 5. Copy app icon
    icon_file = BASE_DIR / "app.ico"
    if icon_file.exists():
        shutil.copy2(icon_file, staging / "app.ico")


def compile_launcher(staging: Path):
    """Biên dịch launcher native ToolEV.exe chạy ngầm kèm icon System Tray"""
    log("Biên dịch launcher native ToolEV.exe (chạy ngầm kèm System Tray Icon)...")
    launcher_cs = BUILD_DIR / "ToolEV_launcher.cs"
    launcher_cs_code = """
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

[assembly: AssemblyTitle("ToolEV")]
[assembly: AssemblyDescription("ToolEV - AI English Learning & IELTS Platform")]
[assembly: AssemblyCompany("Danhiel1")]
[assembly: AssemblyProduct("ToolEV")]
[assembly: AssemblyCopyright("Copyright © 2026 Danhiel1 (nguyenminhhieu.stu@gmail.com)")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

class ToolEVTrayApp : Form {
    private NotifyIcon trayIcon;
    private Process serverProcess;
    private string baseDir;
    private string pythonExe;
    private string serverPy;
    private int port = 8000;

    public ToolEVTrayApp() {
        this.WindowState = FormWindowState.Minimized;
        this.ShowInTaskbar = false;
        this.FormBorderStyle = FormBorderStyle.None;
        this.Opacity = 0;

        baseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\\\', '/');

        // Prefer pythonw.exe (windowless), then python.exe
        pythonExe = Path.Combine(baseDir, "runtime", "pythonw.exe");
        if (!File.Exists(pythonExe)) pythonExe = Path.Combine(baseDir, "runtime", "python.exe");
        if (!File.Exists(pythonExe)) pythonExe = Path.Combine(baseDir, "scripts", ".venv", "Scripts", "pythonw.exe");
        if (!File.Exists(pythonExe)) pythonExe = Path.Combine(baseDir, "scripts", ".venv", "Scripts", "python.exe");
        if (!File.Exists(pythonExe)) pythonExe = "python.exe";

        serverPy = Path.Combine(baseDir, "server.py");

        ContextMenu menu = new ContextMenu();
        menu.MenuItems.Add(new MenuItem("🌐 Mở ToolEV (Giao diện Web)", (s, e) => OpenWeb()));
        menu.MenuItems.Add(new MenuItem("📁 Mở thư mục Bài học (output)", (s, e) => OpenOutputFolder()));
        menu.MenuItems.Add(new MenuItem("📋 Xem nhật ký lỗi (toolev.log)", (s, e) => OpenLogFile()));
        menu.MenuItems.Add("-");
        menu.MenuItems.Add(new MenuItem("👤 Tác giả: Danhiel1 (GitHub)", (s, e) => {
            try { Process.Start(new ProcessStartInfo("https://github.com/Danhiel1/ToolEV") { UseShellExecute = true }); } catch { }
        }));
        menu.MenuItems.Add(new MenuItem("📧 Hỗ trợ: nguyenminhhieu.stu@gmail.com", (s, e) => {
            try { Process.Start(new ProcessStartInfo("mailto:nguyenminhhieu.stu@gmail.com") { UseShellExecute = true }); } catch { }
        }));
        menu.MenuItems.Add("-");
        menu.MenuItems.Add(new MenuItem("🔄 Khởi động lại Server", (s, e) => RestartServer()));
        menu.MenuItems.Add("-");
        menu.MenuItems.Add(new MenuItem("❌ Thoát ToolEV", (s, e) => ExitApp()));

        trayIcon = new NotifyIcon();
        trayIcon.Text = "ToolEV - AI IELTS Platform (Danhiel1)";
        trayIcon.ContextMenu = menu;

        string iconFile = Path.Combine(baseDir, "app.ico");
        if (File.Exists(iconFile)) {
            try { trayIcon.Icon = new Icon(iconFile); }
            catch { trayIcon.Icon = SystemIcons.Application; }
        } else {
            try { trayIcon.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); }
            catch { trayIcon.Icon = SystemIcons.Application; }
        }

        trayIcon.DoubleClick += (s, e) => OpenWeb();
        trayIcon.Visible = true;

        try {
            trayIcon.ShowBalloonTip(3000, "ToolEV đang chạy ngầm", "Nhấp đúp vào biểu tượng ở khay để mở giao diện web bất cứ lúc nào.", ToolTipIcon.Info);
        } catch { }

        StartServer(true);
    }

    protected override void SetVisibleCore(bool value) {
        base.SetVisibleCore(false);
    }

    protected override void OnFormClosing(FormClosingEventArgs e) {
        if (trayIcon != null) {
            trayIcon.Visible = false;
            trayIcon.Dispose();
        }
        StopServer();
        base.OnFormClosing(e);
    }

    private void StartServer(bool openBrowser) {
        try {
            StopServer();

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = string.Format("\\\"{0}\\\" {1}", serverPy, port);
            psi.WorkingDirectory = baseDir;
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;

            string binDir = Path.Combine(baseDir, "bin");
            if (Directory.Exists(binDir)) {
                string oldPath = Environment.GetEnvironmentVariable("PATH") ?? "";
                psi.EnvironmentVariables["PATH"] = binDir + ";" + oldPath;
            }

            serverProcess = Process.Start(psi);

            if (openBrowser) {
                new Thread(() => {
                    Thread.Sleep(1200);
                    OpenWeb();
                }) { IsBackground = true }.Start();
            }
        } catch (Exception ex) {
            MessageBox.Show("Lỗi khởi động ToolEV Server: " + ex.Message, "Lỗi", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void StopServer() {
        if (serverProcess != null && !serverProcess.HasExited) {
            try {
                serverProcess.Kill();
                serverProcess.WaitForExit(1000);
            } catch { }
            serverProcess = null;
        }
    }

    private void RestartServer() {
        StartServer(false);
        try {
            trayIcon.ShowBalloonTip(2000, "ToolEV", "Máy chủ đã được khởi động lại thành công!", ToolTipIcon.Info);
        } catch { }
    }

    private void OpenWeb() {
        try {
            Process.Start(new ProcessStartInfo(string.Format("http://localhost:{0}/all-video.html", port)) { UseShellExecute = true });
        } catch { }
    }

    private void OpenOutputFolder() {
        try {
            string outDir = Path.Combine(baseDir, "output");
            if (!Directory.Exists(outDir)) Directory.CreateDirectory(outDir);
            Process.Start(new ProcessStartInfo("explorer.exe", string.Format("\\\"{0}\\\"", outDir)) { UseShellExecute = true });
        } catch { }
    }

    private void OpenLogFile() {
        try {
            string logFile = Path.Combine(baseDir, "toolev.log");
            if (File.Exists(logFile)) {
                Process.Start(new ProcessStartInfo("notepad.exe", string.Format("\\\"{0}\\\"", logFile)) { UseShellExecute = true });
            } else {
                Process.Start(new ProcessStartInfo(string.Format("http://localhost:{0}/api/logs/raw", port)) { UseShellExecute = true });
            }
        } catch { }
    }

    private void ExitApp() {
        if (trayIcon != null) {
            trayIcon.Visible = false;
            trayIcon.Dispose();
        }
        StopServer();
        this.Close();
        Application.Exit();
    }

    private static bool IsServerAlive(int checkPort) {
        try {
            using (var client = new System.Net.Sockets.TcpClient()) {
                var result = client.BeginConnect("127.0.0.1", checkPort, null, null);
                bool success = result.AsyncWaitHandle.WaitOne(400);
                if (success) {
                    client.EndConnect(result);
                    return true;
                }
            }
        } catch { }
        return false;
    }

    [STAThread]
    static void Main(string[] args) {
        // Neu server da dang chay tren port 8000, mo ngay trinh duyet
        if (IsServerAlive(8000)) {
            try {
                Process.Start(new ProcessStartInfo("http://localhost:8000/all-video.html") { UseShellExecute = true });
            } catch { }
            return;
        }

        // Kiem tra tien trinh launcher da co san trong session
        try {
            Process current = Process.GetCurrentProcess();
            Process[] running = Process.GetProcessesByName(current.ProcessName);
            foreach (Process p in running) {
                if (p.Id != current.Id && p.SessionId == current.SessionId) {
                    Thread.Sleep(800);
                    if (IsServerAlive(8000)) {
                        try { Process.Start(new ProcessStartInfo("http://localhost:8000/all-video.html") { UseShellExecute = true }); } catch { }
                        return;
                    }
                }
            }
        } catch { }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new ToolEVTrayApp());
    }
}
"""


    with open(launcher_cs, "w", encoding="utf-8") as fp:
        fp.write(launcher_cs_code)

    out_exe = staging / "ToolEV.exe"
    cmd = [
        str(CSC_PATH),
        "/target:winexe",
        "/optimize+",
        "/platform:x64",
        f"/out:{out_exe}",
        str(launcher_cs),
        "/r:System.Windows.Forms.dll",
        "/r:System.Drawing.dll"
    ]
    if (BASE_DIR / "app.ico").exists():
        cmd.append(f"/win32icon:{BASE_DIR / 'app.ico'}")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        log(f"Cảnh báo: Không biên dịch được ToolEV.exe: {proc.stderr}")
    else:
        log("Đã tạo ToolEV.exe launcher thành công!")



def test_portable_staging(staging: Path):
    """Chạy thử nghiệm môi trường Portable đã gom"""
    log("Chạy thử nghiệm kiểm tra tính tương thích của Portable Python...")
    test_python = staging / "runtime" / "python.exe"
    if not test_python.exists():
        raise RuntimeError("Không tìm thấy runtime/python.exe trong thư mục staging!")

    test_code = (
        "import sys; "
        "import faster_whisper; "
        "import ctranslate2; "
        "import yt_dlp; "
        "import docx; "
        "import server; "
        "print('PORTABLE_VERIFY_SUCCESS')"
    )
    cmd = [str(test_python), "-c", test_code]
    proc = subprocess.run(cmd, cwd=str(staging), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    if "PORTABLE_VERIFY_SUCCESS" not in proc.stdout:
        raise RuntimeError(f"Kiểm tra Portable thất bại:\nStdout: {proc.stdout}\nStderr: {proc.stderr}")

    log("✅ Kiểm tra Portable Python thành công! Mọi thư viện AI đã sẵn sàng.")


def create_payload_zip(staging: Path, zip_path: Path):
    """Nén thư mục staging thành payload.zip"""
    log(f"Đang nén toàn bộ gói ứng dụng thành {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        total_files = sum(1 for _ in staging.rglob("*") if _.is_file())
        count = 0
        for f in staging.rglob("*"):
            if f.is_file():
                arcname = f.relative_to(staging)
                zf.write(f, arcname)
                count += 1
                if count % 200 == 0:
                    sys.stdout.write(f"\r  -> Tiến độ nén: {count}/{total_files} tệp...")
                    sys.stdout.flush()
        print(f"\r  -> Đã nén xong: {count}/{total_files} tệp.", flush=True)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f"Kích thước gói nén: {size_mb:.1f} MB.")


def compile_sfx_installer(zip_path: Path, output_exe: Path):
    """Biên dịch Self-Extracting Installer (.exe tự bung 1-click)"""
    log("Đang tạo file EXE tự bung (Self-Extracting Installer)...")
    installer_cs = BUILD_DIR / "installer.cs"
    installer_cs_code = """
using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;
using System.Threading;
using System.Diagnostics;

[assembly: AssemblyTitle("ToolEV Setup")]
[assembly: AssemblyDescription("ToolEV Standalone & Portable Installer")]
[assembly: AssemblyCompany("Danhiel1")]
[assembly: AssemblyProduct("ToolEV Setup")]
[assembly: AssemblyCopyright("Copyright © 2026 Danhiel1 (nguyenminhhieu.stu@gmail.com)")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace ToolEVInstaller {
    public class InstallerForm : Form {
        private TextBox txtPath;
        private Button btnBrowse;
        private Button btnInstall;
        private Button btnCancel;
        private CheckBox chkShortcut;
        private CheckBox chkLaunch;
        private ProgressBar progressBar;
        private Label lblStatus;
        private Label lblHeader;
        private Label lblSubHeader;
        private Panel pnlHeader;
        private Thread extractThread;

        public InstallerForm() {
            InitializeComponent();
        }

        private void InitializeComponent() {
            this.Text = "Cài đặt ToolEV - AI English Learning Platform";
            try {
                this.Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
            } catch { }
            this.Size = new Size(540, 400);
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.StartPosition = FormStartPosition.CenterScreen;
            this.Font = new Font("Segoe UI", 9F, FontStyle.Regular);
            this.BackColor = Color.FromArgb(248, 249, 250);

            // Header panel
            pnlHeader = new Panel();
            pnlHeader.Dock = DockStyle.Top;
            pnlHeader.Height = 88;
            pnlHeader.BackColor = Color.FromArgb(15, 23, 42);

            lblHeader = new Label();
            lblHeader.Text = "ToolEV - AI IELTS Study Platform";
            lblHeader.Font = new Font("Segoe UI", 13F, FontStyle.Bold);
            lblHeader.ForeColor = Color.White;
            lblHeader.Location = new Point(20, 12);
            lblHeader.AutoSize = true;

            lblSubHeader = new Label();
            lblSubHeader.Text = "Tự động bung mã nguồn, Python Portable & thư viện AI (Whisper, yt-dlp, ffmpeg)";
            lblSubHeader.Font = new Font("Segoe UI", 8.5F, FontStyle.Regular);
            lblSubHeader.ForeColor = Color.FromArgb(203, 213, 225);
            lblSubHeader.Location = new Point(20, 38);
            lblSubHeader.AutoSize = true;

            Label lblAuthor = new Label();
            lblAuthor.Text = "Tác giả: Danhiel1 • GitHub • Email: nguyenminhhieu.stu@gmail.com";
            lblAuthor.Font = new Font("Segoe UI", 8.5F, FontStyle.Regular);
            lblAuthor.ForeColor = Color.FromArgb(148, 163, 184);
            lblAuthor.Location = new Point(20, 60);
            lblAuthor.AutoSize = true;
            lblAuthor.Cursor = Cursors.Hand;
            lblAuthor.Click += (s, e) => {
                try { Process.Start(new ProcessStartInfo("https://github.com/Danhiel1/ToolEV") { UseShellExecute = true }); } catch { }
            };

            pnlHeader.Controls.Add(lblHeader);
            pnlHeader.Controls.Add(lblSubHeader);
            pnlHeader.Controls.Add(lblAuthor);
            this.Controls.Add(pnlHeader);

            // Path label
            Label lblPath = new Label();
            lblPath.Text = "Thư mục cài đặt / bung ứng dụng:";
            lblPath.Location = new Point(25, 105);
            lblPath.AutoSize = true;
            this.Controls.Add(lblPath);

            // Path textbox
            txtPath = new TextBox();
            txtPath.Location = new Point(25, 130);
            txtPath.Size = new Size(370, 25);
            txtPath.Text = @"C:\\ToolEV";
            this.Controls.Add(txtPath);

            // Browse button
            btnBrowse = new Button();
            btnBrowse.Text = "Chọn...";
            btnBrowse.Location = new Point(405, 128);
            btnBrowse.Size = new Size(95, 29);
            btnBrowse.Click += (s, e) => {
                using (FolderBrowserDialog fbd = new FolderBrowserDialog()) {
                    fbd.Description = "Chọn thư mục bung ToolEV";
                    fbd.SelectedPath = txtPath.Text;
                    if (fbd.ShowDialog() == DialogResult.OK) {
                        txtPath.Text = fbd.SelectedPath;
                    }
                }
            };
            this.Controls.Add(btnBrowse);

            // Checkbox: Desktop shortcut
            chkShortcut = new CheckBox();
            chkShortcut.Text = "Tạo biểu tượng ToolEV ngoài màn hình Desktop";
            chkShortcut.Location = new Point(25, 170);
            chkShortcut.AutoSize = true;
            chkShortcut.Checked = true;
            this.Controls.Add(chkShortcut);

            // Checkbox: Launch after extraction
            chkLaunch = new CheckBox();
            chkLaunch.Text = "Tự động khởi chạy ToolEV ngay sau khi bung xong";
            chkLaunch.Location = new Point(25, 200);
            chkLaunch.AutoSize = true;
            chkLaunch.Checked = true;
            this.Controls.Add(chkLaunch);

            // Status label
            lblStatus = new Label();
            lblStatus.Text = "Sẵn sàng bung ứng dụng. Nhấn 'Bắt đầu' để tiếp tục.";
            lblStatus.Location = new Point(25, 238);
            lblStatus.Size = new Size(475, 20);
            lblStatus.ForeColor = Color.FromArgb(71, 85, 105);
            this.Controls.Add(lblStatus);

            // Progress bar
            progressBar = new ProgressBar();
            progressBar.Location = new Point(25, 260);
            progressBar.Size = new Size(475, 22);
            progressBar.Minimum = 0;
            progressBar.Maximum = 100;
            this.Controls.Add(progressBar);

            // Install button
            btnInstall = new Button();
            btnInstall.Text = "Bắt đầu (Extract)";
            btnInstall.Location = new Point(265, 305);
            btnInstall.Size = new Size(140, 34);
            btnInstall.BackColor = Color.FromArgb(37, 99, 235);
            btnInstall.ForeColor = Color.White;
            btnInstall.FlatStyle = FlatStyle.Flat;
            btnInstall.FlatAppearance.BorderSize = 0;
            btnInstall.Font = new Font("Segoe UI", 9.5F, FontStyle.Bold);
            btnInstall.Click += BtnInstall_Click;
            this.Controls.Add(btnInstall);

            // Cancel button
            btnCancel = new Button();
            btnCancel.Text = "Đóng";
            btnCancel.Location = new Point(415, 305);
            btnCancel.Size = new Size(85, 34);
            btnCancel.Click += (s, e) => { this.Close(); };
            this.Controls.Add(btnCancel);
        }


        private void BtnInstall_Click(object sender, EventArgs e) {
            string dest = txtPath.Text.Trim();
            if (string.IsNullOrEmpty(dest)) {
                MessageBox.Show("Vui lòng chọn thư mục cài đặt!", "Thông báo", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnInstall.Enabled = false;
            btnBrowse.Enabled = false;
            txtPath.Enabled = false;
            chkShortcut.Enabled = false;
            chkLaunch.Enabled = false;

            extractThread = new Thread(() => DoExtract(dest));
            extractThread.IsBackground = true;
            extractThread.Start();
        }

        private void DoExtract(string destDir) {
            try {
                if (!Directory.Exists(destDir)) {
                    Directory.CreateDirectory(destDir);
                }

                // Tự động đóng các tiến trình đang chạy từ thư mục đích để tránh khoá file
                try {
                    string fullDest = Path.GetFullPath(destDir).TrimEnd('\\\\', '/');
                    foreach (Process p in Process.GetProcesses()) {
                        try {
                            string pPath = p.MainModule.FileName;
                            if (pPath.StartsWith(fullDest, StringComparison.OrdinalIgnoreCase)) {
                                p.Kill();
                                p.WaitForExit(1500);
                            }
                        } catch { }
                    }
                } catch { }

                Assembly asm = Assembly.GetExecutingAssembly();
                using (Stream stream = asm.GetManifestResourceStream("payload.zip")) {
                    if (stream == null) {
                        throw new Exception("Không tìm thấy tệp gói nội bộ payload.zip trong trình cài đặt!");
                    }

                    using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read)) {
                        int total = archive.Entries.Count;
                        int count = 0;

                        foreach (ZipArchiveEntry entry in archive.Entries) {
                            count++;
                            int pct = (int)((count * 100.0) / total);

                            this.Invoke((MethodInvoker)delegate {
                                progressBar.Value = Math.Min(100, pct);
                                string name = entry.FullName;
                                if (name.Length > 45) name = "..." + name.Substring(name.Length - 42);
                                lblStatus.Text = string.Format("Đang bung ({0}%): {1}", pct, name);
                            });

                            string targetPath = Path.Combine(destDir, entry.FullName);
                            if (string.IsNullOrEmpty(entry.Name)) {
                                Directory.CreateDirectory(targetPath);
                            } else {
                                string dir = Path.GetDirectoryName(targetPath);
                                if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                                try {
                                    entry.ExtractToFile(targetPath, true);
                                } catch (IOException) {
                                    Thread.Sleep(600);
                                    entry.ExtractToFile(targetPath, true);
                                }
                            }
                        }
                    }
                }

                bool makeShortcut = false;
                bool launch = false;
                this.Invoke((MethodInvoker)delegate {
                    makeShortcut = chkShortcut.Checked;
                    launch = chkLaunch.Checked;
                    progressBar.Value = 100;
                    lblStatus.Text = "Bung hoàn tất 100%!";
                });

                if (makeShortcut) {
                    try {
                        CreateShortcut(destDir);
                    } catch { }
                }

                if (launch) {
                    try {
                        string launcher = Path.Combine(destDir, "ToolEV.exe");
                        if (!File.Exists(launcher)) {
                            launcher = Path.Combine(destDir, "run.bat");
                        }
                        ProcessStartInfo psi = new ProcessStartInfo();
                        psi.FileName = launcher;
                        psi.WorkingDirectory = destDir;
                        psi.UseShellExecute = true;
                        Process.Start(psi);

                    } catch { }
                }

                this.Invoke((MethodInvoker)delegate {
                    MessageBox.Show(
                        "Chúc mừng! ToolEV đã được tự bung ra thành công tại:\\n" + destDir + "\\n\\nỨng dụng đã sẵn sàng sử dụng!",
                        "Cài đặt hoàn tất",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
                    this.Close();
                });
            } catch (Exception ex) {
                this.Invoke((MethodInvoker)delegate {
                    lblStatus.Text = "Lỗi khi bung ứng dụng!";
                    MessageBox.Show("Có lỗi xảy ra: " + ex.Message, "Lỗi", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    btnInstall.Enabled = true;
                    btnBrowse.Enabled = true;
                    txtPath.Enabled = true;
                });
            }
        }

        private void CreateShortcut(string destDir) {
            string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
            string shortcutPath = Path.Combine(desktop, "ToolEV.lnk");

            string targetFile = Path.Combine(destDir, "ToolEV.exe");
            if (!File.Exists(targetFile)) {
                targetFile = Path.Combine(destDir, "run.bat");
            }

            Type shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType != null) {
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = targetFile;
                shortcut.WorkingDirectory = destDir;
                shortcut.Description = "ToolEV - AI English Learning Platform by Danhiel1 (nguyenminhhieu.stu@gmail.com)";

                string iconFile = Path.Combine(destDir, "app.ico");
                if (File.Exists(iconFile)) {
                    shortcut.IconLocation = iconFile + ",0";
                } else if (File.Exists(targetFile)) {
                    shortcut.IconLocation = targetFile + ",0";
                }

                shortcut.Save();
            }
        }

        [STAThread]
        static void Main(string[] args) {
            if (args != null && args.Length > 0) {
                foreach (string a in args) {
                    if (a.Equals("/s", StringComparison.OrdinalIgnoreCase) || a.Equals("/silent", StringComparison.OrdinalIgnoreCase)) {
                        RunSilent(@"C:\\ToolEV");
                        return;
                    }
                }
            }

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }

        static void RunSilent(string destDir) {
            try {
                if (!Directory.Exists(destDir)) Directory.CreateDirectory(destDir);
                Assembly asm = Assembly.GetExecutingAssembly();
                using (Stream stream = asm.GetManifestResourceStream("payload.zip")) {
                    if (stream != null) {
                        using (ZipArchive archive = new ZipArchive(stream, ZipArchiveMode.Read)) {
                            foreach (ZipArchiveEntry entry in archive.Entries) {
                                string targetPath = Path.Combine(destDir, entry.FullName);
                                if (string.IsNullOrEmpty(entry.Name)) Directory.CreateDirectory(targetPath);
                                else {
                                    string dir = Path.GetDirectoryName(targetPath);
                                    if (!Directory.Exists(dir)) Directory.CreateDirectory(dir);
                                    entry.ExtractToFile(targetPath, true);
                                }
                            }
                        }
                    }
                }
                try {
                    string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                    string shortcutPath = Path.Combine(desktop, "ToolEV.lnk");
                    string targetFile = Path.Combine(destDir, "ToolEV.exe");
                    if (!File.Exists(targetFile)) targetFile = Path.Combine(destDir, "run.bat");

                    Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                    if (shellType != null) {
                        dynamic shell = Activator.CreateInstance(shellType);
                        dynamic shortcut = shell.CreateShortcut(shortcutPath);
                        shortcut.TargetPath = targetFile;
                        shortcut.WorkingDirectory = destDir;
                        shortcut.Description = "ToolEV - AI English Learning Platform";
                        string iconFile = Path.Combine(destDir, "app.ico");
                        if (File.Exists(iconFile)) shortcut.IconLocation = iconFile + ",0";
                        shortcut.Save();
                    }
                } catch { }

                string launcher = Path.Combine(destDir, "run.bat");
                if (File.Exists(launcher)) {
                    Process.Start(new ProcessStartInfo(launcher) { WorkingDirectory = destDir });
                }
            } catch { }
        }
    }
}
"""
    with open(installer_cs, "w", encoding="utf-8") as fp:
        fp.write(installer_cs_code)

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(CSC_PATH),
        "/target:winexe",
        "/optimize+",
        "/platform:x64",
        f"/out:{output_exe}",
        f"/resource:{zip_path},payload.zip",
        str(installer_cs),
        "/r:System.Windows.Forms.dll",
        "/r:System.Drawing.dll",
        "/r:System.IO.Compression.dll",
        "/r:System.IO.Compression.FileSystem.dll"
    ]
    if (BASE_DIR / "app.ico").exists():
        cmd.append(f"/win32icon:{BASE_DIR / 'app.ico'}")

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if proc.returncode != 0:
        raise RuntimeError(f"Lỗi biên dịch Installer EXE:\n{proc.stderr}\n{proc.stdout}")

    final_size_mb = output_exe.stat().st_size / (1024 * 1024)
    log(f"🎉 THÀNH CÔNG! Đã tạo file: {output_exe} ({final_size_mb:.1f} MB)")


def main():
    log("Bắt đầu quy trình đóng gói ToolEV Standalone / SFX...")
    clean_dir(BUILD_DIR)
    clean_dir(STAGING_DIR)

    # 1. Prepare Python Portable Runtime
    copy_python_runtime(STAGING_DIR / "runtime")

    # 2. Copy Project Files
    copy_project_files(STAGING_DIR)

    # 3. Compile Launcher
    compile_launcher(STAGING_DIR)

    # 4. Verify Staging
    test_portable_staging(STAGING_DIR)

    # 5. Compress Payload
    payload_zip = BUILD_DIR / "payload.zip"
    create_payload_zip(STAGING_DIR, payload_zip)

    # 6. Compile Final SFX Executable
    final_exe = DIST_DIR / "ToolEV_Setup.exe"
    compile_sfx_installer(payload_zip, final_exe)

    print("\n" + "=" * 60)
    print("🚀 TOOLEV ĐÃ ĐƯỢC ĐÓNG GÓI HOÀN CHỈNH THÀNH 1 FILE EXE DUY NHẤT!")
    print(f"👉 File phát hành: {final_exe}")
    print("👉 Cách dùng: Chỉ cần gửi file này sang bất kỳ máy tính Windows nào,")
    print("   Click đúp vào file là nó sẽ TỰ BUNG RA và CHẠY NGAY LẬP TỨC!")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
