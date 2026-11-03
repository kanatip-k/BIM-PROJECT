using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Plugins;
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;

namespace NavisHeadlessExporter
{
    [Plugin(
        "NavisHeadlessExporter",
        "KNTI",
        DisplayName = "Navis Headless JSON Exporter")]
    public sealed class NavisHeadlessExporterPlugin : AddInPlugin
    {
        public override int Execute(params string[] parameters)
        {
            string outputPath = GetParameter(parameters, 0);
            string statusPath = GetParameter(parameters, 1);

            if (string.IsNullOrWhiteSpace(outputPath))
                return 10;

            outputPath = Path.GetFullPath(outputPath);

            if (string.IsNullOrWhiteSpace(statusPath))
                statusPath = outputPath + ".status.json";
            else
                statusPath = Path.GetFullPath(statusPath);

            try
            {
                Document document = Autodesk.Navisworks.Api.Application.ActiveDocument;

                if (document == null || document.Models.Count == 0)
                {
                    WriteStatus(statusPath, "error", 0, 0, 0,
                        "No Navisworks model is open.");
                    return 11;
                }

                EnsureParentDirectory(outputPath);
                EnsureParentDirectory(statusPath);
                WriteStatus(statusPath, "counting", 0, 0, 0,
                    "Counting physical elements");

                int total = CountPhysicalElements(document, statusPath);

                var snapshot = new ModelSnapshot
                {
                    Source = "Autodesk Navisworks .NET API (NoGui)",
                    ModelName = document.CurrentFileName ?? "Untitled",
                    SnapshotUtc = DateTime.UtcNow.ToString("o"),
                    ElementCount = 0,
                    Elements = new List<ElementDto>(total)
                };

                int processed = 0;

                foreach (Model model in document.Models)
                {
                    foreach (ModelItem item in DescendantsAndSelf(model.RootItem))
                    {
                        if (!IsPhysicalElement(item))
                            continue;

                        processed++;

                        snapshot.Elements.Add(new ElementDto
                        {
                            Id = SafeId(item),
                            DisplayName = item.DisplayName ?? string.Empty,
                            ClassDisplayName = item.ClassDisplayName ?? string.Empty,
                            HasGeometry = SafeHasGeometry(item),
                            Properties = ReadProperties(item)
                        });

                        if (processed % 100 == 0 || processed == total)
                        {
                            int percent = total == 0
                                ? 100
                                : Math.Min(100, (int)((long)processed * 100L / total));

                            WriteStatus(statusPath, "reading", processed, total,
                                percent, "Reading element properties");
                        }
                    }
                }

                snapshot.ElementCount = snapshot.Elements.Count;
                WriteSnapshotAtomically(outputPath, snapshot);

                WriteStatus(statusPath, "complete", snapshot.ElementCount,
                    snapshot.ElementCount, 100, "Export complete");

                return 0;
            }
            catch (Exception exception)
            {
                try
                {
                    WriteStatus(statusPath, "error", 0, 0, 0,
                        exception.ToString());
                }
                catch
                {
                    // The status path itself may be invalid or unwritable.
                }

                return 99;
            }
        }

        private static int CountPhysicalElements(Document document, string statusPath)
        {
            int total = 0;

            foreach (Model model in document.Models)
            {
                foreach (ModelItem item in DescendantsAndSelf(model.RootItem))
                {
                    if (!IsPhysicalElement(item))
                        continue;

                    total++;

                    if (total % 1000 == 0)
                    {
                        WriteStatus(statusPath, "counting", total, 0, 0,
                            "Counting physical elements");
                    }
                }
            }

            return total;
        }

        private static bool IsPhysicalElement(ModelItem item)
        {
            // เดิม: กรองด้วย item.HasGeometry เท่านั้น ซึ่งใน Navisworks tree
            // geometry มักอยู่ที่ node ใบ (Solid fragment) ไม่ใช่ node ระดับ
            // "Element" (เช่น Wall/Door instance เป็น composite ไม่มี geometry ตรงๆ)
            // ผลคือ export ได้แต่ Solid fragment ที่ไม่มี Element.Category/Type/Family
            // เลย (ยืนยันจากไฟล์ export จริง: ทุก element เป็น classDisplayName="Solid"
            // มีแค่ Item/Material/Geometry/Revit Material properties)
            //
            // แก้ใหม่: เลือก node ที่มี PropertyCategory ชื่อ "Element" แทน — นี่คือ
            // node ระดับ family-instance จริง (Wall/Door/Floor/...) ที่มี Category/Type
            // ให้จัด Uniformat ได้ ตรงกับที่ bridge_mock.py ออกแบบไว้ตั้งแต่แรก
            return item != null && HasElementCategory(item);
        }

        private static bool HasElementCategory(ModelItem item)
        {
            try
            {
                foreach (PropertyCategory category in item.PropertyCategories)
                {
                    string name = !string.IsNullOrWhiteSpace(category.DisplayName)
                        ? category.DisplayName
                        : category.Name;

                    if (string.Equals(name, "Element", StringComparison.OrdinalIgnoreCase))
                        return true;
                }
                return false;
            }
            catch
            {
                return false;
            }
        }

        private static IEnumerable<ModelItem> DescendantsAndSelf(ModelItem root)
        {
            if (root == null)
                yield break;

            yield return root;

            foreach (ModelItem child in root.Children)
            {
                foreach (ModelItem descendant in DescendantsAndSelf(child))
                    yield return descendant;
            }
        }

        private static string SafeId(ModelItem item)
        {
            try
            {
                Guid id = item.InstanceGuid;
                return id == Guid.Empty ? string.Empty : id.ToString();
            }
            catch
            {
                return string.Empty;
            }
        }

        private static bool SafeHasGeometry(ModelItem item)
        {
            try
            {
                return item.HasGeometry;
            }
            catch
            {
                return false;
            }
        }

        private static Dictionary<string, string> ReadProperties(ModelItem item)
        {
            var properties = new Dictionary<string, string>();

            foreach (PropertyCategory category in item.PropertyCategories)
            {
                string categoryName = !string.IsNullOrWhiteSpace(category.DisplayName)
                    ? category.DisplayName
                    : category.Name;

                foreach (DataProperty property in category.Properties)
                {
                    string propertyName = !string.IsNullOrWhiteSpace(property.DisplayName)
                        ? property.DisplayName
                        : property.Name;

                    string key = string.Format(
                        "{0}.{1}",
                        categoryName ?? string.Empty,
                        propertyName ?? string.Empty);

                    string value = string.Empty;

                    try
                    {
                        if (property.Value != null)
                            value = property.Value.ToDisplayString();
                    }
                    catch
                    {
                        try
                        {
                            value = property.Value == null
                                ? string.Empty
                                : property.Value.ToString();
                        }
                        catch
                        {
                            value = string.Empty;
                        }
                    }

                    if (!properties.ContainsKey(key))
                        properties.Add(key, value);
                }
            }

            return properties;
        }

        private static void WriteSnapshotAtomically(
            string outputPath,
            ModelSnapshot snapshot)
        {
            string temporaryPath = outputPath + ".writing";

            var serializer = new DataContractJsonSerializer(
                typeof(ModelSnapshot),
                new DataContractJsonSerializerSettings
                {
                    UseSimpleDictionaryFormat = true
                });

            using (var stream = new FileStream(
                temporaryPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.None))
            {
                serializer.WriteObject(stream, snapshot);
            }

            if (File.Exists(outputPath))
                File.Delete(outputPath);

            File.Move(temporaryPath, outputPath);
        }

        private static void WriteStatus(
            string statusPath,
            string phase,
            int processed,
            int total,
            int percent,
            string message)
        {
            var status = new ExportStatus
            {
                Phase = phase ?? string.Empty,
                Processed = processed,
                Total = total,
                Percent = percent,
                Message = message ?? string.Empty,
                UpdatedUtc = DateTime.UtcNow.ToString("o")
            };

            var serializer = new DataContractJsonSerializer(typeof(ExportStatus));
            string temporaryPath = statusPath + ".writing";

            using (var stream = new FileStream(
                temporaryPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.Read))
            {
                serializer.WriteObject(stream, status);
            }

            if (File.Exists(statusPath))
                File.Delete(statusPath);

            File.Move(temporaryPath, statusPath);
        }

        private static void EnsureParentDirectory(string filePath)
        {
            string directory = Path.GetDirectoryName(filePath);

            if (!string.IsNullOrWhiteSpace(directory))
                Directory.CreateDirectory(directory);
        }

        private static string GetParameter(string[] parameters, int index)
        {
            if (parameters == null || index < 0 || index >= parameters.Length)
                return string.Empty;

            return parameters[index] ?? string.Empty;
        }
    }

    [DataContract]
    public sealed class ModelSnapshot
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
    }

    [DataContract]
    public sealed class ElementDto
    {
        [DataMember(Name = "id")]
        public string Id { get; set; }

        [DataMember(Name = "displayName")]
        public string DisplayName { get; set; }

        [DataMember(Name = "classDisplayName")]
        public string ClassDisplayName { get; set; }

        [DataMember(Name = "hasGeometry")]
        public bool HasGeometry { get; set; }

        [DataMember(Name = "properties")]
        public Dictionary<string, string> Properties { get; set; }
    }

    [DataContract]
    public sealed class ExportStatus
    {
        [DataMember(Name = "phase")]
        public string Phase { get; set; }

        [DataMember(Name = "processed")]
        public int Processed { get; set; }

        [DataMember(Name = "total")]
        public int Total { get; set; }

        [DataMember(Name = "percent")]
        public int Percent { get; set; }

        [DataMember(Name = "message")]
        public string Message { get; set; }

        [DataMember(Name = "updatedUtc")]
        public string UpdatedUtc { get; set; }
    }
}
