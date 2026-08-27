using System;
using System.Diagnostics;
using System.IO;

namespace NavisHeadlessRunner
{
    internal static class Program
    {
        private const string PluginId = "NavisHeadlessExporter.KNTI";

        private static int Main(string[] args)
        {
            if (args.Length < 2 || args.Length > 5)
            {
                PrintUsage();
                return 2;
            }

            string modelPath = Path.GetFullPath(args[0]);
            string outputPath = Path.GetFullPath(args[1]);
            string navisworksInstall = args.Length >= 3
                ? Path.GetFullPath(args[2])
                : @"D:\Navisworks Manage 2027";

            string pluginPath = args.Length >= 4
                ? Path.GetFullPath(args[3])
                : Path.Combine(
                    AppDomain.CurrentDomain.BaseDirectory,
                    "NavisHeadlessExporter.dll");

            string statusPath = args.Length >= 5
                ? Path.GetFullPath(args[4])
                : outputPath + ".status.json";

            string roamerPath = Path.Combine(navisworksInstall, "roamer.exe");

            if (!File.Exists(modelPath))
                return Fail("Model file not found: " + modelPath, 3);

            if (!File.Exists(roamerPath))
                return Fail("roamer.exe not found: " + roamerPath, 4);

            if (!File.Exists(pluginPath))
                return Fail("Exporter plug-in not found: " + pluginPath, 5);

            string outputDirectory = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrWhiteSpace(outputDirectory))
                Directory.CreateDirectory(outputDirectory);

            string arguments = string.Join(" ", new[]
            {
                "-NoGui",
                "-AddPluginAssembly", Quote(pluginPath),
                "-OpenFile", Quote(modelPath),
                "-ExecuteAddInPlugin", Quote(PluginId),
                Quote(outputPath), Quote(statusPath),
                "-Exit"
            });

            Console.WriteLine("Starting Navisworks in NoGui mode...");
            Console.WriteLine("Model : " + modelPath);
            Console.WriteLine("Output: " + outputPath);
            Console.WriteLine("Status: " + statusPath);

            var startInfo = new ProcessStartInfo
            {
                FileName = roamerPath,
                Arguments = arguments,
                WorkingDirectory = navisworksInstall,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };

            try
            {
                using (Process process = Process.Start(startInfo))
                {
                    if (process == null)
                        return Fail("Could not start Navisworks.", 6);

                    process.WaitForExit();

                    if (!File.Exists(outputPath))
                    {
                        return Fail(
                            "Navisworks finished but no JSON output was created. " +
                            "Check the status file: " + statusPath,
                            7);
                    }

                    Console.WriteLine("Export completed successfully.");
                    Console.WriteLine("Navisworks exit code: " + process.ExitCode);
                    return 0;
                }
            }
            catch (Exception exception)
            {
                return Fail(exception.ToString(), 99);
            }
        }

        private static string Quote(string value)
        {
            return "\"" + value.Replace("\"", "\\\"") + "\"";
        }

        private static int Fail(string message, int exitCode)
        {
            Console.Error.WriteLine("ERROR: " + message);
            return exitCode;
        }

        private static void PrintUsage()
        {
            Console.WriteLine(
                "Usage:\n" +
                "  NavisHeadlessRunner.exe <model> <output.json> " +
                "[navisworks-folder] [plugin.dll] [status.json]\n\n" +
                "Example:\n" +
                "  NavisHeadlessRunner.exe \"D:\\Models\\Building.nwd\" " +
                "\"D:\\Export\\building.json\" " +
                "\"D:\\Navisworks Manage 2027\"");
        }
    }
}
