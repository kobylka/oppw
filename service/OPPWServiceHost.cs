using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.ServiceProcess;
using System.Text;
using System.Threading;

public sealed class OPPWServiceHost : ServiceBase
{
    private readonly string pythonPath;
    private readonly string supervisorPath;
    private readonly string configPath;
    private readonly string runtimeUserSid;
    private readonly string stopFile;
    private Process child;
    private int childSessionId = -1;
    private Thread monitor;
    private volatile bool stopping;
    private IntPtr job = IntPtr.Zero;

    public OPPWServiceHost(string python, string supervisor, string config, string userSid)
    {
        ServiceName = "OPPWContinuousSupervisor";
        CanStop = true;
        CanShutdown = true;
        CanHandleSessionChangeEvent = true;
        AutoLog = true;
        pythonPath = python;
        supervisorPath = supervisor;
        configPath = config;
        runtimeUserSid = userSid;
        stopFile = config + ".stop";
    }

    protected override void OnStart(string[] args)
    {
        stopping = false;
        if (File.Exists(stopFile)) File.Delete(stopFile);
        CreateKillOnCloseJob();
        monitor = new Thread(MonitorChild);
        monitor.IsBackground = true;
        monitor.Start();
    }

    protected override void OnStop() { StopTree(); }
    protected override void OnShutdown() { StopTree(); }
    protected override void OnSessionChange(SessionChangeDescription changeDescription)
    {
        base.OnSessionChange(changeDescription);
        if (changeDescription.Reason == SessionChangeReason.SessionLogoff &&
            changeDescription.SessionId == childSessionId) StopChildOnly();
    }

    private void MonitorChild()
    {
        while (!stopping)
        {
            try
            {
                if (child == null || child.HasExited) StartChildInInteractiveSession();
            }
            catch (Exception error)
            {
                try { EventLog.WriteEntry(ServiceName, error.Message, EventLogEntryType.Warning); } catch { }
            }
            for (int i = 0; i < 30 && !stopping; i++) Thread.Sleep(1000);
        }
    }

    private void StartChildInInteractiveSession()
    {
        int sessionId;
        IntPtr userToken = FindInteractiveUserToken(runtimeUserSid, out sessionId);
        if (userToken == IntPtr.Zero)
            throw new InvalidOperationException("The configured MetaTrader owner has no active or disconnected Windows session; supervisor launch is waiting for sign-in.");

        IntPtr environment = IntPtr.Zero;
        PROCESS_INFORMATION processInfo = new PROCESS_INFORMATION();
        try
        {
            if (!CreateEnvironmentBlock(out environment, userToken, false)) throw new Win32Exception();
            STARTUPINFO startup = new STARTUPINFO();
            startup.cb = Marshal.SizeOf(typeof(STARTUPINFO));
            startup.lpDesktop = "winsta0\\default";
            StringBuilder command = new StringBuilder(
                Quote(pythonPath) + " " + Quote(supervisorPath) + " --config " + Quote(configPath));
            const uint CreateUnicodeEnvironment = 0x00000400;
            const uint CreateNewProcessGroup = 0x00000200;
            if (!CreateProcessAsUser(userToken, null, command, IntPtr.Zero, IntPtr.Zero, false,
                CreateUnicodeEnvironment | CreateNewProcessGroup, environment,
                Path.GetDirectoryName(supervisorPath), ref startup, out processInfo))
                throw new Win32Exception();
            child = Process.GetProcessById((int)processInfo.dwProcessId);
            childSessionId = sessionId;
            if (job != IntPtr.Zero && !AssignProcessToJobObject(job, child.Handle))
            {
                child.Kill();
                child.WaitForExit(5000);
                throw new Win32Exception();
            }
        }
        finally
        {
            if (processInfo.hThread != IntPtr.Zero) CloseHandle(processInfo.hThread);
            if (processInfo.hProcess != IntPtr.Zero) CloseHandle(processInfo.hProcess);
            if (environment != IntPtr.Zero) DestroyEnvironmentBlock(environment);
            CloseHandle(userToken);
        }
    }

    private static IntPtr FindInteractiveUserToken(string requiredSid, out int selectedSessionId)
    {
        selectedSessionId = -1;
        IntPtr sessions = IntPtr.Zero;
        int count = 0;
        if (!WTSEnumerateSessions(IntPtr.Zero, 0, 1, out sessions, out count)) throw new Win32Exception();
        try
        {
            int size = Marshal.SizeOf(typeof(WTS_SESSION_INFO));
            WTS_CONNECTSTATE_CLASS[] preferredStates = {
                WTS_CONNECTSTATE_CLASS.WTSActive,
                WTS_CONNECTSTATE_CLASS.WTSDisconnected
            };
            foreach (WTS_CONNECTSTATE_CLASS preferredState in preferredStates)
            {
                for (int index = 0; index < count; index++)
                {
                    WTS_SESSION_INFO session = (WTS_SESSION_INFO)Marshal.PtrToStructure(
                        IntPtr.Add(sessions, index * size), typeof(WTS_SESSION_INFO));
                    if (session.State != preferredState) continue;
                    IntPtr token;
                    if (!WTSQueryUserToken((uint)session.SessionID, out token)) continue;
                    try
                    {
                        using (WindowsIdentity identity = new WindowsIdentity(token))
                        {
                            if (identity.User != null &&
                                String.Equals(identity.User.Value, requiredSid, StringComparison.OrdinalIgnoreCase))
                            {
                                selectedSessionId = session.SessionID;
                                return token;
                            }
                        }
                    }
                    catch { }
                    CloseHandle(token);
                }
            }
        }
        finally { if (sessions != IntPtr.Zero) WTSFreeMemory(sessions); }
        return IntPtr.Zero;
    }

    private void StopChildOnly()
    {
        try { File.WriteAllText(stopFile, DateTime.UtcNow.ToString("O")); } catch { }
        if (child != null && !child.HasExited && !child.WaitForExit(30000)) child.Kill();
        child = null;
        childSessionId = -1;
    }

    private void StopTree()
    {
        if (stopping) return;
        stopping = true;
        StopChildOnly();
        if (job != IntPtr.Zero) { CloseHandle(job); job = IntPtr.Zero; }
    }

    private static string Quote(string value) { return "\"" + value.Replace("\"", "\\\"") + "\""; }

    private void CreateKillOnCloseJob()
    {
        job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Win32Exception();
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = 0x00002000;
        int length = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr pointer = Marshal.AllocHGlobal(length);
        try
        {
            Marshal.StructureToPtr(info, pointer, false);
            if (!SetInformationJobObject(job, 9, pointer, (uint)length)) throw new Win32Exception();
        }
        finally { Marshal.FreeHGlobal(pointer); }
    }

    private enum WTS_CONNECTSTATE_CLASS { WTSActive, WTSConnected, WTSConnectQuery, WTSShadow, WTSDisconnected, WTSIdle, WTSListen, WTSReset, WTSDown, WTSInit }
    [StructLayout(LayoutKind.Sequential)] private struct WTS_SESSION_INFO { public int SessionID; public IntPtr WinStationName; public WTS_CONNECTSTATE_CLASS State; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct STARTUPINFO { public int cb; public string lpReserved, lpDesktop, lpTitle; public int dwX, dwY, dwXSize, dwYSize, dwXCountChars, dwYCountChars, dwFillAttribute, dwFlags; public short wShowWindow, cbReserved2; public IntPtr lpReserved2, hStdInput, hStdOutput, hStdError; }
    [StructLayout(LayoutKind.Sequential)] private struct PROCESS_INFORMATION { public IntPtr hProcess, hThread; public uint dwProcessId, dwThreadId; }
    [StructLayout(LayoutKind.Sequential)] private struct IO_COUNTERS { public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount, ReadTransferCount, WriteTransferCount, OtherTransferCount; }
    [StructLayout(LayoutKind.Sequential)] private struct JOBOBJECT_BASIC_LIMIT_INFORMATION { public long PerProcessUserTimeLimit, PerJobUserTimeLimit; public uint LimitFlags; public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize; public uint ActiveProcessLimit; public UIntPtr Affinity; public uint PriorityClass, SchedulingClass; }
    [StructLayout(LayoutKind.Sequential)] private struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION { public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo; public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed; }

    [DllImport("wtsapi32.dll", SetLastError = true)] private static extern bool WTSEnumerateSessions(IntPtr server, int reserved, int version, out IntPtr sessions, out int count);
    [DllImport("wtsapi32.dll")] private static extern void WTSFreeMemory(IntPtr memory);
    [DllImport("wtsapi32.dll", SetLastError = true)] private static extern bool WTSQueryUserToken(uint sessionId, out IntPtr token);
    [DllImport("userenv.dll", SetLastError = true)] private static extern bool CreateEnvironmentBlock(out IntPtr environment, IntPtr token, bool inherit);
    [DllImport("userenv.dll")] private static extern bool DestroyEnvironmentBlock(IntPtr environment);
    [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool CreateProcessAsUser(IntPtr token, string applicationName, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint creationFlags, IntPtr environment, string currentDirectory, ref STARTUPINFO startupInfo, out PROCESS_INFORMATION processInformation);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] private static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll")] private static extern bool SetInformationJobObject(IntPtr job, int infoClass, IntPtr info, uint length);
    [DllImport("kernel32.dll")] private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);

    public static void Main(string[] args)
    {
        if (args.Length != 4) throw new ArgumentException("Expected: <python> <supervisor.py> <config.json> <runtime-user-sid>");
        ServiceBase.Run(new OPPWServiceHost(args[0], args[1], args[2], args[3]));
    }
}
