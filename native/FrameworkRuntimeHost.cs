using System;
using System.Runtime.InteropServices;

public static class FrameworkRuntimeHost
{
    [DllImport("mscoree.dll", PreserveSig = false)]
    private static extern void CLRCreateInstance(ref Guid classId, ref Guid interfaceId, [MarshalAs(UnmanagedType.Interface)] out object instance);

    [ComImport, Guid("D332DB9E-B9B3-4125-8207-A14884F53216"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMetaHost
    {
        [return: MarshalAs(UnmanagedType.Interface)] object GetRuntime([MarshalAs(UnmanagedType.LPWStr)] string version, ref Guid interfaceId);
    }

    [ComImport, Guid("BD39D1D2-BA2F-486A-89B0-B4B0CB466891"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IRuntimeInfo
    {
        void GetVersionString(IntPtr buffer, ref uint size);
        void GetRuntimeDirectory(IntPtr buffer, ref uint size);
        [return: MarshalAs(UnmanagedType.Bool)] bool IsLoaded(IntPtr process);
        void LoadErrorString(uint resource, IntPtr buffer, ref uint size, int locale);
        IntPtr LoadLibrary([MarshalAs(UnmanagedType.LPWStr)] string name);
        IntPtr GetProcAddress([MarshalAs(UnmanagedType.LPStr)] string name);
        [return: MarshalAs(UnmanagedType.Interface)] object GetInterface(ref Guid classId, ref Guid interfaceId);
    }

    [ComImport, Guid("90F1A06C-7712-4762-86B5-7A5EBA6BDB02"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IRuntimeHost
    {
        void Start();
        void Stop();
        void SetHostControl(IntPtr control);
        IntPtr GetCLRControl();
        void UnloadAppDomain(uint domain, [MarshalAs(UnmanagedType.Bool)] bool wait);
        void ExecuteInAppDomain(uint domain, IntPtr callback, IntPtr cookie);
        uint GetCurrentAppDomainId();
        void ExecuteApplication([MarshalAs(UnmanagedType.LPWStr)] string app, uint manifestCount, IntPtr manifests, uint dataCount, IntPtr data);
        void ExecuteInDefaultAppDomain([MarshalAs(UnmanagedType.LPWStr)] string assembly,
            [MarshalAs(UnmanagedType.LPWStr)] string type, [MarshalAs(UnmanagedType.LPWStr)] string method,
            [MarshalAs(UnmanagedType.LPWStr)] string argument, out uint result);
    }

    public static int Execute(string assemblyPath, string arguments)
    {
        Guid metaClass = new Guid("9280188D-0E8E-4867-B30C-7FA83884E8DE");
        Guid metaInterface = typeof(IMetaHost).GUID;
        object metaObject;
        CLRCreateInstance(ref metaClass, ref metaInterface, out metaObject);
        IMetaHost meta = (IMetaHost)metaObject;
        Guid infoInterface = typeof(IRuntimeInfo).GUID;
        IRuntimeInfo info = (IRuntimeInfo)meta.GetRuntime("v4.0.30319", ref infoInterface);
        Guid hostClass = new Guid("90F1A06E-7712-4762-86B5-7A5EBA6BDB02");
        Guid hostInterface = typeof(IRuntimeHost).GUID;
        IRuntimeHost host = (IRuntimeHost)info.GetInterface(ref hostClass, ref hostInterface);
        host.Start();
        uint result;
        host.ExecuteInDefaultAppDomain(assemblyPath, "NativeHeadless", "FrameworkEntry", arguments, out result);
        return unchecked((int)result);
    }
}
