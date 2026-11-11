using System;
using System.Collections.Generic;
using System.IO;
using QSR.NVivo.Common.Business.Services;

public sealed class NativeConverterController : IConverterController
{
    public NativeConverterController(object connection, object importer, string input)
    {
        ProjectConnection = (ProjectConnection)connection;
        SourceImporter = (ISourceImporter)importer;
        InputFilename = input;
        ConverterErrors = new List<n9>();
    }
    public bool IsCancelled { get { return false; } }
    public string InputFilename { get; private set; }
    public string RelativeBasePath { get { return Path.GetDirectoryName(InputFilename); } }
    public bool CodeDocumentsAtCases { get { return false; } }
    public bool ImportTextStyles { get { return false; } }
    public bool ImportColor { get { return true; } }
    public string Username { get { return ""; } }
    public string Password { get { return ""; } }
    public ProjectConnection ProjectConnection { get; private set; }
    public string StartupPath { get { return Environment.GetEnvironmentVariable("NVIVO_INSTALL_DIR"); } }
    public List<n9> ConverterErrors { get; set; }
    public ISourceImporter SourceImporter { get; private set; }
    public void OnWorkerCompleted() { Console.WriteLine("CONVERTER completed"); }
    public void OnWorkerCancelled() { throw new InvalidOperationException("Converter cancelled"); }
    public void OnWorkerFailed(Exception error) { throw new InvalidOperationException("Converter failed", error); }
    public void OnWorkerInitalizeStage(int stage, int size) { Console.WriteLine("CONVERTER stage=" + stage + " size=" + size); }
    public void OnWorkerProgress(int value) { }
}
