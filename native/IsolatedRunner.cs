using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Reflection;

public static class IsolatedRunner
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct StartupInfo
    {
        public int cb;
        public string reserved;
        public string desktop;
        public string title;
        public int x, y, width, height, charX, charY, fill, flags;
        public short show, reservedSize;
        public IntPtr reservedPointer, input, output, error;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct ProcessInfo { public IntPtr process, thread; public int processId, threadId; }
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateDesktop(string desktop, IntPtr device, IntPtr mode, int flags, uint access, IntPtr security);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool CloseDesktop(IntPtr desktop);
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool SetThreadDesktop(IntPtr desktop);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateProcess(string app, StringBuilder command, IntPtr processSecurity, IntPtr threadSecurity,
        bool inherit, uint flags, IntPtr environment, string directory, ref StartupInfo startup, out ProcessInfo process);
    [DllImport("kernel32.dll")]
    private static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll")]
    private static extern bool GetExitCodeProcess(IntPtr handle, out uint code);
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    public static int RunManaged(string assemblyPath, string logPath, string[] arguments)
    {
        TextWriter originalOutput = Console.Out;
        TextWriter originalError = Console.Error;
        string originalDirectory = Environment.CurrentDirectory;
        string originalLog = Environment.GetEnvironmentVariable("NVIVO_HEADLESS_LOG");
        string originalDesktop = Environment.GetEnvironmentVariable("NVIVO_HEADLESS_DESKTOP");
        string name = "NVivoHeadless_" + Guid.NewGuid().ToString("N");
        IntPtr desktop = CreateDesktop(name, IntPtr.Zero, IntPtr.Zero, 0, 0x01ff, IntPtr.Zero);
        if (desktop == IntPtr.Zero) throw new Win32Exception();
        int result = 1;
        Exception failure = null;
        Thread worker = new Thread(delegate()
        {
            try
            {
                if (!SetThreadDesktop(desktop)) throw new Win32Exception();
                Environment.SetEnvironmentVariable("NVIVO_HEADLESS_DESKTOP", name);
                Environment.SetEnvironmentVariable("NVIVO_HEADLESS_LOG", Path.GetFullPath(logPath));
                result = FrameworkRuntimeHost.Execute(Path.GetFullPath(assemblyPath), String.Join("\n", arguments));
            }
            catch (Exception error) { failure = error; }
        });
        worker.SetApartmentState(ApartmentState.STA);
        try
        {
            worker.Start();
            worker.Join();
            if (failure != null) throw new InvalidOperationException("Isolated backend failed", failure);
            return result;
        }
        finally
        {
            TextWriter backendOutput = Console.Out;
            Console.SetOut(originalOutput);
            Console.SetError(originalError);
            if (!Object.ReferenceEquals(backendOutput, originalOutput)) backendOutput.Dispose();
            Environment.CurrentDirectory = originalDirectory;
            Environment.SetEnvironmentVariable("NVIVO_HEADLESS_LOG", originalLog);
            Environment.SetEnvironmentVariable("NVIVO_HEADLESS_DESKTOP", originalDesktop);
            CloseDesktop(desktop);
        }
    }

    public static int Main(string[] args)
    {
        if (args.Length < 2) throw new ArgumentException("Usage: IsolatedRunner <program> <log> [program arguments]");
        string name = "NVivoHeadless_" + Guid.NewGuid().ToString("N");
        IntPtr desktop = CreateDesktop(name, IntPtr.Zero, IntPtr.Zero, 0, 0x01ff, IntPtr.Zero);
        if (desktop == IntPtr.Zero) throw new Win32Exception();
        ProcessInfo process = new ProcessInfo();
        try
        {
            string program = Path.GetFullPath(args[0]);
            string log = Path.GetFullPath(args[1]);
            Environment.SetEnvironmentVariable("NVIVO_HEADLESS_LOG", log);
            StartupInfo startup = new StartupInfo();
            startup.cb = Marshal.SizeOf(typeof(StartupInfo));
            startup.desktop = "WinSta0\\" + name;
            startup.flags = 1;
            startup.show = 0;
            StringBuilder command = new StringBuilder("\"" + program + "\"");
            for (int i = 2; i < args.Length; i++)
            {
                if (args[i].Contains("\"")) throw new ArgumentException("Quoted program arguments are unsupported");
                command.Append(" \"").Append(args[i]).Append("\"");
            }
            if (!CreateProcess(program, command, IntPtr.Zero, IntPtr.Zero, false, 0x08000000,
                IntPtr.Zero, Path.GetDirectoryName(program), ref startup, out process)) throw new Win32Exception();
            Console.WriteLine("Isolated desktop worker PID=" + process.processId + ", desktop=" + name);
            // 只创建隔离桌面并等待后台进程，全程保持当前用户桌面。
            WaitForSingleObject(process.process, 0xffffffff);
            uint code;
            GetExitCodeProcess(process.process, out code);
            if (File.Exists(log)) Console.Write(File.ReadAllText(log));
            Console.WriteLine("WorkerExitCode=" + code);
            return unchecked((int)code);
        }
        finally
        {
            if (process.thread != IntPtr.Zero) CloseHandle(process.thread);
            if (process.process != IntPtr.Zero) CloseHandle(process.process);
            CloseDesktop(desktop);
        }
    }
}
