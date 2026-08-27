using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Plugins;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Threading;

namespace NavisMcpBridge
{
    [Plugin("NavisMcpBridge", "KNTI", DisplayName = "Navis MCP Bridge")]
    public class NavisMcpBridgePlugin : AddInPlugin
    {
        public override int Execute(params string[] parameters)
        {
            ExtractionProgressForm progressForm = null;

            try
            {
                var doc = Autodesk.Navisworks.Api.Application.ActiveDocument;
                if (doc == null || doc.Models.Count == 0)
                {
                    System.Windows.Forms.MessageBox.Show(
                        "Please open an NWD, NWF, or NWC model first.",
                        "Navis MCP Bridge");
                    return -1;
                }

                progressForm = new ExtractionProgressForm();
                progressForm.Show();
                progressForm.BringToFront();
                System.Windows.Forms.Application.DoEvents();

                var snapshot = SnapshotBuilder.Build(
                    doc,
                    progressForm.UpdateProgress,
                    delegate { return progressForm.CancellationRequested; });

                BridgeState.SetSnapshot(snapshot);
                BridgeServer.Start();

                progressForm.MarkComplete(snapshot.ElementCount);
                System.Windows.Forms.Application.DoEvents();

                System.Windows.Forms.MessageBox.Show(
                    "Navisworks snapshot ready.\n\n" +
                    "Elements read: " + snapshot.ElementCount.ToString("N0") + "\n" +
                    "Bridge: http://127.0.0.1:8765/api/elements\n\n" +
                    "You can now click Refresh from MCP on the web dashboard.",
                    "Navis MCP Bridge");

                return 0;
            }
            catch (OperationCanceledException)
            {
                System.Windows.Forms.MessageBox.Show(
                    "Reading was cancelled. The previous snapshot was not replaced.",
                    "Navis MCP Bridge");
                return -1;
            }
            catch (Exception ex)
            {
                System.Windows.Forms.MessageBox.Show(ex.ToString(), "Navis MCP Bridge Error");
                return -1;
            }
            finally
            {
                if (progressForm != null)
                {
                    progressForm.CloseSafely();
                    progressForm.Dispose();
                }
            }
        }
    }

    public static class SnapshotBuilder
    {
        public static ModelSnapshot Build(
            Document doc,
            Action<ExtractionProgress> reportProgress,
            Func<bool> isCancellationRequested)
        {
            var elements = new List<ElementDto>();
            int total = 0;

            Report(reportProgress, "Counting physical elements...", 0, 0);

            foreach (var model in doc.Models)
            {
                foreach (var item in DescendantsAndSelf(model.RootItem))
                {
                    ThrowIfCancelled(isCancellationRequested);

                    if (!IsPhysicalElement(item))
                        continue;

                    total++;

                    if (total % 1000 == 0)
                        Report(reportProgress, "Counting physical elements...", total, 0);
                }
            }

            Report(reportProgress, "Reading physical element properties...", 0, total);

            int processed = 0;

            foreach (var model in doc.Models)
            {
                foreach (var item in DescendantsAndSelf(model.RootItem))
                {
                    ThrowIfCancelled(isCancellationRequested);

                    if (!IsPhysicalElement(item))
                        continue;

                    processed++;

                    var dto = new ElementDto
                    {
                        Id = SafeId(item),
                        DisplayName = item.DisplayName ?? "",
                        ClassDisplayName = item.ClassDisplayName ?? "",
                        Properties = ReadProperties(item)
                    };

                    elements.Add(dto);

                    if (processed % 25 == 0 || processed == total)
                    {
                        Report(
                            reportProgress,
                            "Reading physical element properties...",
                            processed,
                            total);
                    }
                }
            }

            return new ModelSnapshot
            {
                Source = "Autodesk Navisworks .NET API",
                ModelName = doc.CurrentFileName ?? "Untitled",
                SnapshotUtc = DateTime.UtcNow.ToString("o"),
                ElementCount = elements.Count,
                Elements = elements
            };
        }

        private static void Report(
            Action<ExtractionProgress> reportProgress,
            string phase,
            int processed,
            int total)
        {
            if (reportProgress == null)
                return;

            reportProgress(new ExtractionProgress
            {
                Phase = phase,
                Processed = processed,
                Total = total
            });
        }

        private static void ThrowIfCancelled(Func<bool> isCancellationRequested)
        {
            if (isCancellationRequested != null && isCancellationRequested())
                throw new OperationCanceledException();
        }

        private static bool IsPhysicalElement(ModelItem item)
        {
            try
            {
                return item != null && item.HasGeometry;
            }
            catch
            {
                return false;
            }
        }

        private static IEnumerable<ModelItem> DescendantsAndSelf(ModelItem root)
        {
            yield return root;
            foreach (var child in root.Children)
            {
                foreach (var x in DescendantsAndSelf(child))
                    yield return x;
            }
        }

        private static string SafeId(ModelItem item)
        {
            try { return item.InstanceGuid.ToString(); }
            catch { return Guid.NewGuid().ToString(); }
        }

        private static Dictionary<string, string> ReadProperties(ModelItem item)
        {
            var result = new Dictionary<string, string>();

            foreach (PropertyCategory cat in item.PropertyCategories)
            {
                string catName = !string.IsNullOrWhiteSpace(cat.DisplayName)
                    ? cat.DisplayName
                    : cat.Name;

                foreach (DataProperty prop in cat.Properties)
                {
                    string propName = !string.IsNullOrWhiteSpace(prop.DisplayName)
                        ? prop.DisplayName
                        : prop.Name;

                    string key = string.Format("{0}.{1}", catName, propName);
                    string value = "";

                    try
                    {
                        if (prop.Value != null)
                            value = prop.Value.ToDisplayString();
                    }
                    catch
                    {
                        try { value = prop.Value == null ? "" : prop.Value.ToString(); } catch { }
                    }

                    if (!result.ContainsKey(key))
                        result[key] = value;
                }
            }

            return result;
        }
    }

    public class ExtractionProgress
    {
        public string Phase { get; set; }
        public int Processed { get; set; }
        public int Total { get; set; }
    }

    public sealed class ExtractionProgressForm : System.Windows.Forms.Form
    {
        private readonly System.Windows.Forms.Label _statusLabel;
        private readonly System.Windows.Forms.Label _countLabel;
        private readonly System.Windows.Forms.ProgressBar _progressBar;
        private readonly System.Windows.Forms.Button _cancelButton;
        private bool _allowClose;

        public bool CancellationRequested { get; private set; }

        public ExtractionProgressForm()
        {
            Text = "Navis MCP Bridge - Reading model";
            Width = 520;
            Height = 190;
            StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog;
            MaximizeBox = false;
            MinimizeBox = false;

            _statusLabel = new System.Windows.Forms.Label
            {
                Dock = System.Windows.Forms.DockStyle.Top,
                Height = 42,
                Padding = new System.Windows.Forms.Padding(12, 10, 12, 0),
                Text = "Preparing..."
            };

            _countLabel = new System.Windows.Forms.Label
            {
                Dock = System.Windows.Forms.DockStyle.Top,
                Height = 30,
                Padding = new System.Windows.Forms.Padding(12, 6, 12, 0),
                Text = "0 elements"
            };

            _progressBar = new System.Windows.Forms.ProgressBar
            {
                Dock = System.Windows.Forms.DockStyle.Top,
                Height = 24,
                Style = System.Windows.Forms.ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 30
            };

            _cancelButton = new System.Windows.Forms.Button
            {
                Dock = System.Windows.Forms.DockStyle.Bottom,
                Height = 36,
                Text = "Cancel"
            };
            _cancelButton.Click += delegate
            {
                CancellationRequested = true;
                _cancelButton.Enabled = false;
                _statusLabel.Text = "Cancelling...";
            };

            Controls.Add(_cancelButton);
            Controls.Add(_progressBar);
            Controls.Add(_countLabel);
            Controls.Add(_statusLabel);

            FormClosing += delegate(object sender, System.Windows.Forms.FormClosingEventArgs e)
            {
                if (!_allowClose)
                {
                    CancellationRequested = true;
                    e.Cancel = true;
                }
            };
        }

        public void UpdateProgress(ExtractionProgress progress)
        {
            _statusLabel.Text = progress.Phase;

            if (progress.Total <= 0)
            {
                _progressBar.Style = System.Windows.Forms.ProgressBarStyle.Marquee;
                _countLabel.Text = progress.Processed.ToString("N0") + " elements found";
            }
            else
            {
                int percent = Math.Min(100, (int)((long)progress.Processed * 100 / progress.Total));
                _progressBar.Style = System.Windows.Forms.ProgressBarStyle.Continuous;
                _progressBar.Value = percent;
                _countLabel.Text = string.Format(
                    "{0:N0} / {1:N0} elements ({2}%)",
                    progress.Processed,
                    progress.Total,
                    percent);
            }

            Refresh();
            System.Windows.Forms.Application.DoEvents();
        }

        public void MarkComplete(int elementCount)
        {
            _progressBar.Style = System.Windows.Forms.ProgressBarStyle.Continuous;
            _progressBar.Value = 100;
            _statusLabel.Text = "Snapshot complete";
            _countLabel.Text = elementCount.ToString("N0") + " elements read (100%)";
            Refresh();
        }

        public void CloseSafely()
        {
            _allowClose = true;
            Close();
        }
    }

    public static class BridgeState
    {
        private static readonly object Sync = new object();
        private static ModelSnapshot _snapshot = new ModelSnapshot();

        public static void SetSnapshot(ModelSnapshot snapshot)
        {
            lock (Sync) { _snapshot = snapshot; }
        }

        public static string GetJson()
        {
            lock (Sync)
            {
                var serializer = new DataContractJsonSerializer(
                    typeof(ModelSnapshot),
                    new DataContractJsonSerializerSettings
                    {
                        UseSimpleDictionaryFormat = true
                    });

                using (var stream = new MemoryStream())
                {
                    serializer.WriteObject(stream, _snapshot);
                    return Encoding.UTF8.GetString(stream.ToArray());
                }
            }
        }
    }

    public static class BridgeServer
    {
        private static HttpListener _listener;
        private static Thread _thread;

        public static void Start()
        {
            if (_listener != null && _listener.IsListening) return;

            _listener = new HttpListener();
            _listener.Prefixes.Add("http://127.0.0.1:8765/");
            _listener.Start();

            _thread = new Thread(ListenLoop) { IsBackground = true };
            _thread.Start();
        }

        private static void ListenLoop()
        {
            while (_listener != null && _listener.IsListening)
            {
                try
                {
                    var ctx = _listener.GetContext();

                    if (ctx.Request.Url.AbsolutePath.Equals("/api/elements", StringComparison.OrdinalIgnoreCase))
                    {
                        WriteJson(ctx, 200, BridgeState.GetJson());
                    }
                    else
                    {
                        WriteJson(ctx, 404, "{\"error\":\"not found\"}");
                    }
                }
                catch
                {
                    // Keep prototype bridge alive while Navisworks is running.
                }
            }
        }

        private static void WriteJson(HttpListenerContext ctx, int status, string json)
        {
            byte[] data = Encoding.UTF8.GetBytes(json);
            ctx.Response.StatusCode = status;
            ctx.Response.ContentType = "application/json; charset=utf-8";
            ctx.Response.ContentLength64 = data.Length;
            ctx.Response.OutputStream.Write(data, 0, data.Length);
            ctx.Response.OutputStream.Close();
        }
    }

    [DataContract]
    public class ModelSnapshot
    {
        [DataMember(Name = "source")]
        public string Source { get; set; }

        [DataMember(Name = "modelName")]
        public string ModelName { get; set; }

        [DataMember(Name = "snapshotUtc")]
        public string SnapshotUtc { get; set; }

        [DataMember(Name = "elementCount")]
        public int ElementCount { get; set; }

        [DataMember(Name = "elements")]
        public List<ElementDto> Elements { get; set; }

        public ModelSnapshot()
        {
            Source = "";
            ModelName = "";
            SnapshotUtc = "";
            Elements = new List<ElementDto>();
        }
    }

    [DataContract]
    public class ElementDto
    {
        [DataMember(Name = "id")]
        public string Id { get; set; }

        [DataMember(Name = "displayName")]
        public string DisplayName { get; set; }

        [DataMember(Name = "classDisplayName")]
        public string ClassDisplayName { get; set; }

        [DataMember(Name = "properties")]
        public Dictionary<string, string> Properties { get; set; }

        public ElementDto()
        {
            Id = "";
            DisplayName = "";
            ClassDisplayName = "";
            Properties = new Dictionary<string, string>();
        }
    }
}
