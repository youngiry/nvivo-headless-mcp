using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Configuration;
using System.Data.SqlClient;
using System.Collections;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;
using System.Security.Cryptography;

public static class NativeHeadless
{
    private static readonly string Vendor = Environment.GetEnvironmentVariable("NVIVO_INSTALL_DIR");
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string path);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryEx(string path, IntPtr file, uint flags);

    public static int FrameworkEntry(string arguments)
    {
        AppDomainSetup setup = new AppDomainSetup();
        setup.ApplicationBase = Vendor;
        setup.ConfigurationFile = Path.Combine(Vendor, "NVivo.exe.config");
        AppDomain domain = AppDomain.CreateDomain("NVivoNativeConversion", null, setup);
        try
        {
            FrameworkWorker worker = (FrameworkWorker)domain.CreateInstanceFromAndUnwrap(
                Assembly.GetExecutingAssembly().Location, typeof(FrameworkWorker).FullName);
            return worker.Run(arguments);
        }
        finally { AppDomain.Unload(domain); }
    }

    public sealed class FrameworkWorker : MarshalByRefObject
    {
        public int Run(string arguments) { return Main(arguments.Split('\n')); }
        public override object InitializeLifetimeService() { return null; }
    }

    [STAThread]
    public static int Main(string[] args)
    {
        Console.OutputEncoding = Encoding.UTF8;
        string logPath = Environment.GetEnvironmentVariable("NVIVO_HEADLESS_LOG");
        if (!String.IsNullOrEmpty(logPath))
        {
            StreamWriter log = new StreamWriter(logPath, false, new UTF8Encoding(false));
            log.AutoFlush = true;
            Console.SetOut(log);
            Console.SetError(log);
        }
        Environment.CurrentDirectory = Vendor;
        AppDomain.CurrentDomain.AssemblyResolve += Resolve;
        try
        {
            if (args.Length > 0 && args[0] == "dllprobe")
            {
                SetDllDirectory(Vendor);
                IntPtr module = LoadLibraryEx(Path.Combine(Vendor, "tx151.dll"), IntPtr.Zero, 8);
                if (module == IntPtr.Zero) throw new System.ComponentModel.Win32Exception();
                Console.WriteLine("Native text kernel loaded");
                return 0;
            }
            if (args.Length > 0 && args[0] == "sqlprobe")
            {
                using (SqlConnection sql = new SqlConnection(args[1]))
                {
                    Console.WriteLine("SQL opening");
                    sql.Open();
                    Console.WriteLine("SQL connected, version " + sql.ServerVersion);
                }
                return 0;
            }
            Assembly common = Assembly.LoadFrom(Path.Combine(Vendor, "QSR.NVivo.Common.Business.dll"));
            Assembly client = Assembly.LoadFrom(Path.Combine(Vendor, "QSR.NVivo.Client.Business.dll"));
            if (args.Length == 0 || args[0] == "inspect")
            {
                foreach (string interfaceName in new[] {
                    "QSR.NVivo.Common.Business.Services.ISourceImporter",
                    "QSR.NVivo.Common.Business.Domain.ISummaryContentLengthFinder" })
                {
                    Type contract = common.GetType(interfaceName, true);
                    foreach (string file in new[] { "QSR.NVivo.Common.Business.dll", "QSR.NVivo.Client.Business.dll", "NVivo.exe" })
                    {
                        Assembly assembly = Assembly.LoadFrom(Path.Combine(Vendor, file));
                        Type[] types;
                        try { types = assembly.GetTypes(); }
                        catch (ReflectionTypeLoadException error) { types = error.Types; }
                        foreach (Type type in types.Where(type => type != null && !type.IsInterface && contract.IsAssignableFrom(type)))
                        {
                            Console.WriteLine("IMPLEMENTATION " + interfaceName + " : " + type.FullName + " in " + file);
                            foreach (ConstructorInfo constructor in type.GetConstructors()) Console.WriteLine(constructor);
                        }
                    }
                }
                return 0;
            }
            if ((args[0] != "create" && args[0] != "build" && args[0] != "verify") || args.Length < 2)
                throw new ArgumentException("Usage: inspect | create <new-project-path> | build <new-project-path> <native-xml>");
            string target = Path.GetFullPath(args[1]);
            if (args[0] != "verify" && File.Exists(target)) throw new IOException("Temporary project already exists. Inspect before retrying.");
            Type applicationService = common.GetType("QSR.NVivo.Common.Business.Services.ApplicationService", true);
            Type configurationType = common.GetType("QSR.NVivo.Common.Business.Services.ApplicationConfiguration", true);
            object configuration = Activator.CreateInstance(configurationType);
            configurationType.GetProperty("SqlConnectionTimeout").SetValue(configuration, "5", null);
            Type userType = common.GetType("QSR.NVivo.Common.Business.Domain.StandaloneUserProfile", true);
            object user = Activator.CreateInstance(userType);
            userType.GetProperty("Name").SetValue(user, Environment.GetEnvironmentVariable("NVIVO_AUTHOR") ?? "Shalom", null);
            Type projectUserType = common.GetType("QSR.NVivo.Common.Business.Domain.ProjectUserProfile", true);
            object projectUser = Activator.CreateInstance(projectUserType);
            projectUserType.GetProperty("ActiveStandaloneUserProfile", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(projectUser, user, null);
            configurationType.GetProperty("CurrentUser").SetValue(configuration, projectUser, null);
            applicationService.GetProperty("Configuration").SetValue(null, configuration, null);
            Console.WriteLine("CONFIGURATION initialized");
            Type projectService = common.GetType("QSR.NVivo.Common.Business.Services.ProjectService", true);
            object connection;
            if (args[0] == "build" || args[0] == "verify" || args[0] == "create")
            {
                AppDomain.CurrentDomain.SetData("APP_CONTEXT_BASE_DIRECTORY", Vendor + Path.DirectorySeparatorChar);
                Console.WriteLine("NATIVE LIBRARY BASE=" + AppDomain.CurrentDomain.BaseDirectory);
                if (!SetDllDirectory(Vendor)) throw new System.ComponentModel.Win32Exception();
                if (LoadLibraryEx(Path.Combine(Vendor, "tx151.dll"), IntPtr.Zero, 8) == IntPtr.Zero)
                    throw new System.ComponentModel.Win32Exception();
                Assembly forms = Assembly.Load("System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089");
                Type applicationType = forms.GetType("System.Windows.Forms.Application", true);
                Type exceptionMode = forms.GetType("System.Windows.Forms.UnhandledExceptionMode", true);
                applicationType.GetMethod("SetUnhandledExceptionMode", new Type[] { exceptionMode, typeof(bool) })
                    .Invoke(null, new object[] { Enum.Parse(exceptionMode, "ThrowException"), true });
                Assembly presentation = Assembly.LoadFrom(Path.Combine(Vendor, "NVivo.exe"));
                string helperFolder = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                Assembly sourceBackend = Assembly.LoadFrom(Path.Combine(helperFolder, "HeadlessSourceImporter.dll"));
                object sourceImporter = Activator.CreateInstance(sourceBackend.GetType("HeadlessSourceImporter", true));
                Console.WriteLine("SOURCE IMPORTER initialized");
                if (args[0] == "verify")
                {
                    MethodInfo open = projectService.GetMethods().Single(method => method.Name == "OpenProject" && method.GetParameters().Length == 8);
                    connection = open.Invoke(null, new object[] { target, true, false, true, null, null, false, sourceImporter });
                    Console.WriteLine("PROJECT reopened: " + target);
                    try { DumpProject(common, connection, Path.GetFullPath(args[2])); }
                    finally { projectService.GetMethod("CloseProject", Type.EmptyTypes).Invoke(null, null); }
                    Console.WriteLine("PROJECT verified and closed");
                    return 0;
                }
                Type language = common.GetType("QSR.NVivo.Common.Business.Domain.IndexLanguageType", true);
                Type connectionType = common.GetType("QSR.NVivo.Common.Business.Services.ProjectConnection", true);
                connection = Activator.CreateInstance(connectionType);
                projectService.GetProperty("ActiveConnection").SetValue(null, connection, null);
                string title = Environment.GetEnvironmentVariable("NVIVO_PROJECT_TITLE") ?? Path.GetFileNameWithoutExtension(target);
                connectionType.GetMethod("CreateProject").Invoke(connection, new object[] { target, title, "编码材料与分析记录", false, null, null, Enum.Parse(language, "Chinese"), true });
                projectService.GetProperty("ActiveConnection").SetValue(null, connection, null);
                Console.WriteLine("PROJECT initialized: " + target);
                IDictionary folders = (IDictionary)connectionType.GetProperty("SystemFolderMap").GetValue(connection, null);
                Type folderKind = common.GetType("QSR.NVivo.Common.Business.Domain.FolderContentsType", true);
                object internalFolder = folders[Enum.Parse(folderKind, "Internal")];
                object mappers = connectionType.GetProperty("Mappers", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).GetValue(connection, null);
                object sourceMapper = mappers.GetType().GetProperty("SourceMapper").GetValue(mappers, null);
                sourceMapper.GetType().GetProperty("SummaryContentLengthFinder").SetValue(sourceMapper, sourceImporter, null);
                object session = mappers.GetType().GetProperty("DbSession").GetValue(mappers, null);
                object sql = session.GetType().GetProperty("SqlConnection").GetValue(session, null);
                projectService.GetField("mySqlConnection", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, sql);
                Type transactions = common.GetType("QSR.NVivo.Common.Business.Services.TransactionService", true);
                transactions.GetMethod("Open").Invoke(null, null);
                object transaction = Activator.CreateInstance(common.GetType("QSR.NVivo.Common.Business.Services.SystemBusinessTransaction", true), new object[] { null });
                transactions.GetMethod("StartBusinessTransaction").Invoke(null, new object[] { transaction });
                Type catalogue = common.GetType("QSR.NVivo.Common.Business.Services.CatalogueService", true);
                catalogue.GetMethod("OpenProject", new Type[] { typeof(bool), typeof(bool) }).Invoke(null, new object[] { true, false });
                transactions.GetMethod("CommitBusinessTransaction").Invoke(null, null);
                transactions.GetMethod("Save", Type.EmptyTypes).Invoke(null, null);
                Console.WriteLine("CATALOGUE initialized");
                if (args[0] == "create")
                {
                    projectService.GetMethod("CloseProject", Type.EmptyTypes).Invoke(null, null);
                    Console.WriteLine("PROJECT created and closed");
                    return 0;
                }
                System.Xml.XmlDocument importDocument = new System.Xml.XmlDocument();
                importDocument.PreserveWhitespace = true;
                importDocument.Load(Path.GetFullPath(args[2]));
                string importAuthor = Environment.GetEnvironmentVariable("NVIVO_AUTHOR") ?? "Shalom";
                foreach (System.Xml.XmlNode memberName in importDocument.SelectNodes(
                    "//*[local-name()='creationMemberName' or local-name()='modificationMemberName'] | //*[local-name()='member']/*[local-name()='name']"))
                    memberName.InnerText = importAuthor;
                importDocument.Save(Path.GetFullPath(args[2]));
                Assembly controllerAssembly = Assembly.LoadFrom(Path.Combine(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location), "NativeConverterController.dll"));
                object controller = Activator.CreateInstance(controllerAssembly.GetType("NativeConverterController", true), new object[] { connection, sourceImporter, Path.GetFullPath(args[2]) });
                Type importerType = common.GetType("QSR.NVivo.Common.Business.Services.ConverterWorker", true);
                object importer = Activator.CreateInstance(importerType, new object[] { controller });
                importerType.GetField("myOutputFilename", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(importer, Path.GetFullPath(args[2]));
                FieldInfo projectKind = importerType.GetField("mySourceProjectType", BindingFlags.NonPublic | BindingFlags.Instance);
                projectKind.SetValue(importer, Enum.Parse(projectKind.FieldType, "QDPX"));
                Console.WriteLine("IMPORT starting");
                importerType.GetMethod("Import", BindingFlags.NonPublic | BindingFlags.Instance).Invoke(importer, null);
                transactions.GetMethod("CommitDataTransaction").Invoke(null, null);
                transactions.GetMethod("Save", Type.EmptyTypes).Invoke(null, null);
                string memoLinksPath = Path.ChangeExtension(Path.GetFullPath(args[2]), ".memo-links.json");
                if (File.Exists(memoLinksPath)) ApplyMemoLinks(common, transactions, memoLinksPath);
                ICollection warnings = (ICollection)importerType.GetField("myConverterErrors", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(importer);
                Console.WriteLine("IMPORT warning count=" + warnings.Count);
                Console.WriteLine("IMPORT completed");
            }
            else
            {
                connection = projectService.GetMethod("CreateEmptyLocalProject").Invoke(null, new object[] { target });
                Console.WriteLine("PROJECT created: " + target);
            }
            if (connection != null)
            {
                if (args[0] == "build") projectService.GetMethod("CloseProject", Type.EmptyTypes).Invoke(null, null);
                else connection.GetType().GetMethod("CloseProject", Type.EmptyTypes).Invoke(connection, null);
                Console.WriteLine("PROJECT closed");
            }
            return 0;
        }
        catch (Exception error)
        {
            for (Exception item = error; item != null; item = item.InnerException)
            {
                Console.Error.WriteLine(item.GetType().FullName + ": " + item.Message);
                Console.Error.WriteLine(item.StackTrace);
            }
            return 1;
        }
    }

    private static Assembly Resolve(object sender, ResolveEventArgs args)
    {
        string path = Path.Combine(Vendor, new AssemblyName(args.Name).Name + ".dll");
        return File.Exists(path) ? Assembly.LoadFrom(path) : null;
    }

    private static void ApplyMemoLinks(Assembly common, Type transactions, string path)
    {
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        List<Dictionary<string, string>> links = serializer.Deserialize<List<Dictionary<string, string>>>(File.ReadAllText(path));
        Dictionary<string, object> sources = new Dictionary<string, object>();
        foreach (object source in (IEnumerable)common.GetType("QSR.NVivo.Common.Business.Services.SourceService", true).GetMethod("FindAllSources").Invoke(null, null))
            sources[(string)Value(source, "Name")] = source;
        Dictionary<string, object> nodes = new Dictionary<string, object>();
        Type findIn = common.GetType("QSR.NVivo.Common.Business.Domain.FindIn", true);
        foreach (object node in (IEnumerable)common.GetType("QSR.NVivo.Common.Business.Services.NodeService", true).GetMethod("FindAll").Invoke(null, new object[] { Enum.Parse(findIn, "Database") }))
            nodes[(string)Value(node, "Name")] = node;
        object transaction = Activator.CreateInstance(common.GetType("QSR.NVivo.Common.Business.Services.SystemBusinessTransaction", true), new object[] { null });
        transactions.GetMethod("StartBusinessTransaction").Invoke(null, new object[] { transaction });
        Type taskType = common.GetType("QSR.NVivo.Common.Business.Services.CreateMemoLinkTask", true);
        foreach (Dictionary<string, string> link in links)
        {
            object item = link["kind"] == "source" ? sources[link["item"]] : nodes[link["item"]];
            object task = Activator.CreateInstance(taskType, new object[] { item, sources[link["memo"]] });
            transaction.GetType().GetMethod("AddTask").Invoke(transaction, new object[] { task });
        }
        transactions.GetMethod("CommitBusinessTransaction").Invoke(null, null);
        transactions.GetMethod("CommitDataTransaction").Invoke(null, null);
        transactions.GetMethod("Save", Type.EmptyTypes).Invoke(null, null);
        Console.WriteLine("MEMO LINKS created=" + links.Count);
    }

    private static object Value(object item, string property)
    {
        for (Type type = item.GetType(); type != null; type = type.BaseType)
        {
            PropertyInfo info = type.GetProperty(property, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            if (info != null && info.GetGetMethod(true) != null) return info.GetValue(item, null);
        }
        throw new MissingMemberException(item.GetType().FullName, property);
    }

    private static void DumpProject(Assembly common, object connection, string output)
    {
        List<Dictionary<string, object>> sources = new List<Dictionary<string, object>>();
        Type sourceService = common.GetType("QSR.NVivo.Common.Business.Services.SourceService", true);
        foreach (object source in (IEnumerable)sourceService.GetMethod("FindAllSources").Invoke(null, null))
        {
            byte[] content = (byte[])Value(source, "Content");
            string contentHash;
            using (SHA256 hash = SHA256.Create()) contentHash = BitConverter.ToString(hash.ComputeHash(content)).Replace("-", "").ToLowerInvariant();
            sources.Add(new Dictionary<string, object> {
                { "name", Value(source, "Name") }, { "text", Value(source, "PlainTextContent") }, { "type", source.GetType().Name }, { "created_by", Value(Value(source, "CreatedBy"), "Name") }, { "modified_by", Value(Value(source, "ModifiedBy"), "Name") }, { "description", Value(source, "Description") },
                { "content_bytes", content.Length }, { "content_sha256", contentHash }
            });
            object sourceMemo = Value(source, "LinkedMemo");
            sources[sources.Count - 1]["linked_memo"] = sourceMemo == null ? null : Value(sourceMemo, "Name");
        }
        Type nodeService = common.GetType("QSR.NVivo.Common.Business.Services.NodeService", true);
        Console.WriteLine("READBACK loaded documents=" + sources.Count);
        Type findIn = common.GetType("QSR.NVivo.Common.Business.Domain.FindIn", true);
        List<Dictionary<string, object>> nodes = new List<Dictionary<string, object>>();
        List<Dictionary<string, object>> references = new List<Dictionary<string, object>>();
        foreach (object node in (IEnumerable)nodeService.GetMethod("FindAll").Invoke(null, new object[] { Enum.Parse(findIn, "Database") }))
        {
            string name = (string)Value(node, "Name");
            Dictionary<string, object> nodeState = new Dictionary<string, object> { { "created_by", Value(Value(node, "CreatedBy"), "Name") }, { "description", Value(node, "Description") }, { "name", name }, { "type", node.GetType().Name }, { "hierarchy", Value(node, "HierarchicalName") } };
            if (node.GetType().Name == "Case")
            {
                Dictionary<string, string> attributes = new Dictionary<string, string>();
                foreach (object value in (IEnumerable)Value(node, "AttributeValues"))
                    attributes[(string)Value(Value(value, "Attribute"), "Name")] = (string)Value(value, "Name");
                nodeState["attributes"] = attributes;
            }
            nodes.Add(nodeState);
            object parentNode = Value(node, "Parent");
            nodeState["parent"] = parentNode == null ? null : Value(parentNode, "Name");
            nodeState["folder"] = Value(Value(node, "ContainingFolder"), "Name");
            object linkedMemo = Value(node, "LinkedMemo");
            nodeState["linked_memo"] = linkedMemo == null ? null : Value(linkedMemo, "Name");
            int referenceCount = 0;
            foreach (object reference in (IEnumerable)Value(node, "NodeReferences"))
            {
                referenceCount++;
                object source = Value(reference, "Source");
                string text = (string)Value(source, "PlainTextContent");
                object range = Value(reference, "Range");
                int start = range == null ? 0 : (int)Value(range, "StartPosition");
                int length = range == null ? text.Length : (int)Value(range, "Length");
                references.Add(new Dictionary<string, object> {
                    { "created_by", Value(Value(reference, "CreatedBy"), "Name") }, { "node", name }, { "source", Value(source, "Name") }, { "start", start }, { "length", length },
                    { "text", text.Substring(start, length) }, { "reference_type", Value(reference, "ReferenceType").ToString() }
                });
            }
            nodeState["reference_count"] = referenceCount;
        }
        List<Dictionary<string, object>> folderState = new List<Dictionary<string, object>>();
        Type folderService = common.GetType("QSR.NVivo.Common.Business.Services.FolderService", true);
        IDictionary systemFolders = (IDictionary)folderService.GetMethod("GetSystemFolders").Invoke(null, null);
        foreach (DictionaryEntry entry in systemFolders)
        {
            List<string> contents = new List<string>();
            foreach (object item in (IEnumerable)Value(entry.Value, "ContentsExcludingSubfolders"))
                contents.Add((string)Value(item, "Name"));
            folderState.Add(new Dictionary<string, object> {
                { "kind", entry.Key.ToString() }, { "name", Value(entry.Value, "Name") }, { "contents", contents }
            });
        }
        JavaScriptSerializer serializer = new JavaScriptSerializer();
        serializer.MaxJsonLength = Int32.MaxValue;
        File.WriteAllText(output, serializer.Serialize(new Dictionary<string, object> {
            { "project_created_by", Value(Value(Value(connection, "Project"), "CreatedBy"), "Name") },
            { "project_title", Value(Value(connection, "Project"), "Name") },
            { "readback_project_file", Value(Value(connection, "InstanceIdentifier"), "FilePath") },
            { "runtime", Environment.Version.ToString() },
            { "background_desktop", Environment.GetEnvironmentVariable("NVIVO_HEADLESS_DESKTOP") },
            { "sources", sources }, { "nodes", nodes }, { "references", references }, { "system_folders", folderState }
        }), new UTF8Encoding(false));
        Console.WriteLine("READBACK sources=" + sources.Count + " nodes=" + nodes.Count + " references=" + references.Count);
    }
}
