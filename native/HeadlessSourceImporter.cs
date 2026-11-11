using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.ComponentModel;
using QSR.NVivo.Client.Presentation.CommandHandlers;
using QSR.NVivo.Common.Business.Domain;
using QSR.NVivo.Common.Business.Services;

public sealed class HeadlessSourceImporter : SourceCommandHandler, ISourceImporter
{
    private sealed class VendorResourceLicenseContext : LicenseContext
    {
        private readonly LicenseContext original;
        private readonly Assembly vendor;
        public VendorResourceLicenseContext(LicenseContext originalContext, Assembly vendorAssembly)
        {
            original = originalContext;
            vendor = vendorAssembly;
        }
        public override LicenseUsageMode UsageMode { get { return LicenseUsageMode.Runtime; } }
        public override string GetSavedLicenseKey(Type type, Assembly resourceAssembly)
        {
            // 标准运行时资源查找，组件提供程序执行其正常许可证验证。
            return original.GetSavedLicenseKey(type, resourceAssembly ?? vendor);
        }
        public override void SetSavedLicenseKey(Type type, string key) { original.SetSavedLicenseKey(type, key); }
    }
    // 输入为研究材料的纯文本。使用NVivo自带文本引擎生成其原生存储内容。
    // 控件句柄在独立隐藏桌面中创建，宿主窗体全程保持隐藏。
    public new void LoadFromString(TextSource source, string text, bool isRichText, bool applyHeading,
        List<TextStyle> styles, bool sourceIsLegacy)
    {
        if (isRichText) throw new InvalidOperationException("This conversion expects plain text materials");
        if (String.IsNullOrEmpty(Environment.GetEnvironmentVariable("NVIVO_HEADLESS_DESKTOP")))
            throw new InvalidOperationException("Native text conversion requires the isolated background desktop");
        Assembly presentation = typeof(SourceCommandHandler).Assembly;
        LicenseContext originalContext = LicenseManager.CurrentContext;
        LicenseManager.CurrentContext = new VendorResourceLicenseContext(originalContext, presentation);
        Type type = presentation.GetType("QSR.NVivo.Client.Presentation.Controls.BaseTextControl", true);
        object control = Activator.CreateInstance(type, new object[] { false });
        Type formType = Assembly.Load("System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089").GetType("System.Windows.Forms.Form", true);
        object form = Activator.CreateInstance(formType);
        try
        {
            formType.GetProperty("ShowInTaskbar").SetValue(form, false, null);
            formType.GetProperty("Opacity").SetValue(form, 0.0, null);
            object collection = formType.GetProperty("Controls").GetValue(form, null);
            collection.GetType().GetMethods().Single(method => method.Name == "Add" && method.GetParameters().Length == 1).Invoke(collection, new object[] { control });
            formType.GetProperty("Handle").GetValue(form, null);
            type.GetProperty("Handle").GetValue(control, null);
            formType.GetMethod("Show", Type.EmptyTypes).Invoke(form, null);
            type.GetMethod("f7", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).Invoke(control, null);
            type.GetMethod("a", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance, null,
                new Type[] { typeof(string), typeof(bool), typeof(bool) }, null).Invoke(control, new object[] { text, false, false });
            source.Content = (byte[])type.GetMethod("fq", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).Invoke(control, null);
            source.PlainTextContent = (string)type.GetProperty("PlainTextContent").GetValue(control, null);
            if (Canonical(text).TrimEnd('\n') != Canonical(source.PlainTextContent).TrimEnd('\n'))
                throw new InvalidOperationException("Native document text differs from the confirmed workbook record");
            IList targetParagraphs = (IList)typeof(TextSource).GetProperty("ParagraphList").GetValue(source, null);
            targetParagraphs.Clear();
            IEnumerable paragraphs = (IEnumerable)type.GetProperty("ParagraphList").GetValue(control, null);
            foreach (object paragraph in paragraphs) targetParagraphs.Add(paragraph);
        }
        finally
        {
            ((IDisposable)form).Dispose();
            ((IDisposable)control).Dispose();
            LicenseManager.CurrentContext = originalContext;
        }
    }

    private static string Canonical(string text) { return text.Replace("\r\n", "\n").Replace('\r', '\n'); }
}
