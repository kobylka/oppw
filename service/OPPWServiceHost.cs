using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.ServiceProcess;
using System.Threading;

public sealed class OPPWServiceHost : ServiceBase
{
    private readonly string pythonPath;
    private readonly string supervisorPath;
    private readonly string configPath;
    private readonly string stopFile;
    private Process child;
    private Thread monitor;
    private volatile bool stopping;
    private IntPtr job = IntPtr.Zero;

    public OPPWServiceHost(string python, string supervisor, string config)
    {
        ServiceName = "OPPWContinuousSupervisor";
        CanStop = true;
        CanShutdown = true;
        AutoLog = true;
        pythonPath = python;
        supervisorPath = supervisor;
        configPath = config;
        stopFile = config + ".stop";
    }

    protected override void OnStart(string[] args)
    {
        stopping = false;
        if (File.Exists(stopFile)) File.Delete(stopFile);
        CreateKillOnCloseJob();
        StartChild();
        monitor = new Thread(MonitorChild);
        monitor.IsBackground = true;
        monitor.Start();
    }

    protected override void OnStop() { StopTree(); }
    protected override void OnShutdown() { StopTree(); }

    private void MonitorChild()
    {
        while (!stopping)
        {
            if (child == null || child.HasExited)
            {
                Thread.Sleep(3000);
                if (!stopping) StartChild();
            }
            Thread.Sleep(1000);
        }
    }

    private void StartChild()
    {
        ProcessStartInfo start = new ProcessStartInfo();
        start.FileName = pythonPath;
        start.Arguments = Quote(supervisorPath) + " --config " + Quote(configPath);
        start.WorkingDirectory = Path.GetDirectoryName(supervisorPath);
        start.UseShellExecute = false;
        start.CreateNoWindow = true;
        child = Process.Start(start);
        if (job != IntPtr.Zero && child != null && !AssignProcessToJobObject(job, child.Handle))
        {
            child.Kill();
            child.WaitForExit(5000);
            throw new System.ComponentModel.Win32Exception();
        }
    }

    private void StopTree()
    {
        if (stopping) return;
        stopping = true;
        try { File.WriteAllText(stopFile, DateTime.UtcNow.ToString("O")); } catch { }
        if (child != null && !child.HasExited)
        {
            if (!child.WaitForExit(30000)) child.Kill();
        }
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
    }

    private static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }

    private void CreateKillOnCloseJob()
    {
        job = CreateJobObject(IntPtr.Zero, null);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = 0x00002000;
        int length = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr pointer = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(info, pointer, false);
            if (!SetInformationJobObject(job, 9, pointer, (uint)length)) throw new System.ComponentModel.Win32Exception();
        }
        finally { Marshal.FreeHGlobal(pointer); }
    }

    [StructLayout(LayoutKind.Sequential)] private struct IO_COUNTERS { public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] private struct JOBOBJECT_BASIC_LIMIT_INFORMATION { public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass, SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")] private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
    [DllImport("kernel32.dll")] private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);

    public static void Main(string[] args)
    {
        if (args.Length != 3) throw new ArgumentException("Expected: <python> <supervisor.py> <config.json>");
        ServiceBase.Run(new OPPWServiceHost(args[0], args[1], args[2]));
    }
}
