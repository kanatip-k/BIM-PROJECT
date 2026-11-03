using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Plugins;

namespace NavisMCPExporter
{
    /// <summary>
    /// Navisworks add-in plugin (net48) that walks the currently open model,
    /// reads each item's properties and geometry flags, classifies it into a
    /// UNIFORMAT II cost code, and writes a JSON snapshot to the output path
    /// passed on the command line.
    ///
    /// Invoked headless via:
    ///   roamer.exe -NoGui -AddPluginAssembly NavisMCP.Exporter.dll
    ///     -OpenFile model.nwc -ExecuteAddInPlugin NavisMCPExporter.KNTI
    ///     &lt;outputPath&gt; &lt;statusPath&gt; -Exit
    /// </summary>
    [Plugin("NavisMCPExporter", "KNTI", DisplayName = "NavisMCP NWC Exporter")]
    public class NwcExporterPlugin : AddInPlugin
    {
        public override int Execute(params string[] parameters)
        {
            string outputPath = parameters.Length > 0 ? parameters[0] : "export.json";
            string statusPath = parameters.Length > 1 ? parameters[1] : outputPath + ".status.json";

            try
            {
                WriteStatus(statusPath, "reading", 0, 0, "Opening model");

                var doc = Application.ActiveDocument;
                var rootItems = doc.Models.RootItems;

                var elements = new List<ElementDto>();
                var all = new List<ModelItem>();
                foreach (ModelItem root in rootItems)
                {
                    CollectDescendants(root, all);
                }

                int total = all.Count;
                int processed = 0;
                int skipped = 0;

                foreach (var item in all)
                {
                    processed++;

                    // Drop non-BOQ scaffolding (Solid / Type / Family / Category /
                    // rooms / grids …) at the source so the snapshot only carries
                    // quantifiable Revit instances. The real instances one level up
                    // hold the Area/Volume/Length properties, so nothing is lost.
                    if (!UniformatClassifier.IsBoqElement(
                            item.ClassDisplayName ?? "", item.DisplayName ?? ""))
                    {
                        skipped++;
                        continue;
                    }

                    elements.Add(BuildDto(item));

                    if (processed % 5000 == 0)
                    {
                        int pct = total > 0 ? (int)(100L * processed / total) : 0;
                        WriteStatus(statusPath, "reading", processed, total,
                            "Reading elements (skipped " + skipped + " non-BOQ)", pct);
                    }
                }

                WriteStatus(statusPath, "writing", processed, total, "Writing snapshot", 99);

                var snapshot = new ModelSnapshot
                {
                    Source = "navisworks",
                    ModelName = SafeModelName(doc),
                    SnapshotUtc = DateTime.UtcNow.ToString("o"),
                    CoordinateUnits = doc.Units.ToString(),
                    ElementCount = elements.Count,
                    Elements = elements,
                };

                WriteJson(outputPath, snapshot);
                WriteStatus(statusPath, "done", processed, total, "Export complete", 100);
                return 0;
            }
            catch (Exception ex)
            {
                WriteStatus(statusPath, "error", 0, 0, ex.Message);
                return 1;
            }
        }

        private static void CollectDescendants(ModelItem item, List<ModelItem> sink)
        {
            sink.Add(item);
            foreach (ModelItem child in item.Children)
            {
                CollectDescendants(child, sink);
            }
        }

        private static ElementDto BuildDto(ModelItem item)
        {
            string classDisplayName = item.ClassDisplayName ?? "";
            string displayName = item.DisplayName ?? "";
            var uniformat = UniformatClassifier.Classify(classDisplayName, displayName);

            var dto = new ElementDto
            {
                Id = ReadInstanceGuid(item),
                DisplayName = displayName,
                ClassDisplayName = classDisplayName,
                HasGeometry = item.HasGeometry,
                IsHidden = item.IsHidden,
                AncestorPath = BuildAncestorPath(item),
                SourceFileName = SafeSourceFile(item),
                CoordinateUnits = Application.ActiveDocument.Units.ToString(),
                Properties = ReadProperties(item),
                ClassificationEvidence = ReadClassificationEvidence(item),
                BoundingBox = ReadBBox(item),
                UniformatCode = uniformat.Code,
                UniformatTitle = uniformat.Title,
                BoqEligible = UniformatClassifier.IsBoqElement(classDisplayName, displayName),
            };
            return dto;
        }

        private static string ReadInstanceGuid(ModelItem item)
        {
            try
            {
                if (item.InstanceGuid != Guid.Empty)
                    return item.InstanceGuid.ToString();
            }
            catch { }
            return "";
        }

        private static string BuildAncestorPath(ModelItem item)
        {
            var parts = new List<string>();
            var cur = item;
            while (cur != null)
            {
                if (!string.IsNullOrEmpty(cur.DisplayName))
                    parts.Insert(0, cur.DisplayName);
                cur = cur.Parent;
            }
            return string.Join(" > ", parts.ToArray());
        }

        private static string SafeSourceFile(ModelItem item)
        {
            try
            {
                var root = item;
                while (root.Parent != null) root = root.Parent;
                return root.DisplayName ?? "";
            }
            catch { return ""; }
        }

        private static string SafeModelName(Document doc)
        {
            try
            {
                if (doc.Models.Count > 0)
                    return Path.GetFileName(doc.Models[0].FileName) ?? doc.Title;
            }
            catch { }
            return doc.Title ?? "model";
        }

        private static Dictionary<string, string> ReadProperties(ModelItem item)
        {
            var result = new Dictionary<string, string>();
            foreach (PropertyCategory cat in item.PropertyCategories)
            {
                string catName = cat.DisplayName ?? cat.Name ?? "";
                foreach (DataProperty prop in cat.Properties)
                {
                    string key = catName + "." + (prop.DisplayName ?? prop.Name ?? "");
                    string value = FormatValue(prop.Value);
                    if (!result.ContainsKey(key))
                        result[key] = value;
                }
            }
            return result;
        }

        // Keep native classification evidence separate from derived UNIFORMAT.
        // Ancestor inheritance is restricted to Type/Family, never category/root.
        private static List<ClassificationPropertyDto> ReadClassificationEvidence(ModelItem item)
        {
            var result = new List<ClassificationPropertyDto>();
            int distance = 0;
            for (var node = item; node != null; node = node.Parent, distance++)
            {
                string nodeClass = node.ClassDisplayName ?? "";
                if (distance > 0 && nodeClass != "Type" && nodeClass != "Family") continue;
                foreach (PropertyCategory cat in node.PropertyCategories)
                foreach (DataProperty prop in cat.Properties)
                {
                    string key = (cat.DisplayName ?? cat.Name ?? "") + "." + (prop.DisplayName ?? prop.Name ?? "");
                    string internalKey = (cat.Name ?? "") + "." + (prop.Name ?? "");
                    string normal = System.Text.RegularExpressions.Regex.Replace((key + internalKey).ToLowerInvariant(), "[^a-z0-9]", "");
                    string kind = null;
                    foreach (string token in new[] { "assemblycode", "assemblydescription", "omniclass", "keynote", "masterformat", "uniformat", "omniformat", "classification" })
                        if (normal.Contains(token)) { kind = token; break; }
                    if (kind == null) continue;
                    string value = FormatValue(prop.Value);
                    if (String.IsNullOrWhiteSpace(value)) continue;
                    result.Add(new ClassificationPropertyDto {
                        Kind = kind, PropertyKey = key, InternalPropertyKey = internalKey,
                        Value = value, SourceNodeClass = nodeClass,
                        SourceNodeName = node.DisplayName ?? "", SourcePath = BuildAncestorPath(node),
                        SourceFileName = SafeSourceFile(node), AncestorDistance = distance
                    });
                }
            }
            return result;
        }

        private static string FormatValue(VariantData v)
        {
            if (v == null) return "";
            try
            {
                switch (v.DataType)
                {
                    case VariantDataType.DisplayString: return v.ToDisplayString();
                    case VariantDataType.IdentifierString: return v.ToIdentifierString();
                    case VariantDataType.Boolean: return v.ToBoolean().ToString();
                    case VariantDataType.Double: return "Double:" + v.ToDouble();
                    case VariantDataType.DoubleArea: return "DoubleArea:" + v.ToDoubleArea();
                    case VariantDataType.DoubleLength: return "DoubleLength:" + v.ToDoubleLength();
                    case VariantDataType.DoubleVolume: return "DoubleVolume:" + v.ToDoubleVolume();
                    case VariantDataType.Int32: return v.ToInt32().ToString();
                    case VariantDataType.NamedConstant: return v.ToNamedConstant().DisplayName;
                    case VariantDataType.DateTime: return v.ToDateTime().ToString("o");
                    default: return v.ToString();
                }
            }
            catch
            {
                return "";
            }
        }

        private static BBoxDto ReadBBox(ModelItem item)
        {
            try
            {
                var bb = item.BoundingBox();
                if (bb == null || bb.IsEmpty) return null;
                double[] values = { bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z };
                foreach (double value in values)
                    if (double.IsNaN(value) || double.IsInfinity(value)) return null;
                return new BBoxDto
                {
                    MinX = bb.Min.X, MinY = bb.Min.Y, MinZ = bb.Min.Z,
                    MaxX = bb.Max.X, MaxY = bb.Max.Y, MaxZ = bb.Max.Z,
                };
            }
            catch
            {
                return null;
            }
        }

        // Hand-written JSON writer so the output matches exactly what the .NET 10
        // server (System.Text.Json) expects: `properties` is a plain object
        // {"key":"value"}, numbers use invariant formatting, booleans lower-case.
        private static void WriteJson(string path, ModelSnapshot snapshot)
        {
            var dir = Path.GetDirectoryName(path);
            if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);

            using (var w = new StreamWriter(File.Create(path), new UTF8Encoding(false)))
            {
                w.Write("{");
                w.Write("\"source\":"); WriteStr(w, snapshot.Source); w.Write(",");
                w.Write("\"modelName\":"); WriteStr(w, snapshot.ModelName); w.Write(",");
                w.Write("\"snapshotUtc\":"); WriteStr(w, snapshot.SnapshotUtc); w.Write(",");
                w.Write("\"classificationEvidenceSchemaVersion\":\"1.0\",\"spatialSchemaVersion\":\"1.0\",\"coordinateFrame\":\"navisworks-document\",\"crossModelAlignmentVerified\":false,");
                w.Write("\"coordinateUnits\":"); WriteStr(w, snapshot.CoordinateUnits); w.Write(",");
                w.Write("\"elementCount\":"); w.Write(snapshot.ElementCount.ToString(Inv)); w.Write(",");
                w.Write("\"elements\":[");
                var els = snapshot.Elements;
                for (int i = 0; i < els.Count; i++)
                {
                    if (i > 0) w.Write(",");
                    WriteElement(w, els[i]);
                }
                w.Write("]}");
            }
        }

        private static void WriteElement(TextWriter w, ElementDto e)
        {
            w.Write("{");
            w.Write("\"id\":"); WriteStr(w, e.Id); w.Write(",");
            w.Write("\"displayName\":"); WriteStr(w, e.DisplayName); w.Write(",");
            w.Write("\"classDisplayName\":"); WriteStr(w, e.ClassDisplayName); w.Write(",");
            w.Write("\"hasGeometry\":"); w.Write(e.HasGeometry ? "true" : "false"); w.Write(",");
            w.Write("\"isHidden\":"); w.Write(e.IsHidden ? "true" : "false"); w.Write(",");
            w.Write("\"ancestorPath\":"); WriteStr(w, e.AncestorPath); w.Write(",");
            w.Write("\"sourceFileName\":"); WriteStr(w, e.SourceFileName); w.Write(",");
            w.Write("\"uniformatCode\":"); WriteStr(w, e.UniformatCode); w.Write(",");
            w.Write("\"uniformatTitle\":"); WriteStr(w, e.UniformatTitle); w.Write(",");
            w.Write("\"boqEligible\":"); w.Write(e.BoqEligible ? "true" : "false"); w.Write(",");
            w.Write("\"classificationEvidence\":{");
            w.Write("\"schemaVersion\":\"1.0\",\"nativeProperties\":[");
            var evidence = e.ClassificationEvidence;
            for (int i = 0; evidence != null && i < evidence.Count; i++)
            {
                if (i > 0) w.Write(",");
                var row = evidence[i];
                w.Write("{");
                w.Write("\"kind\":"); WriteStr(w, row.Kind); w.Write(",");
                w.Write("\"propertyKey\":"); WriteStr(w, row.PropertyKey); w.Write(",");
                w.Write("\"internalPropertyKey\":"); WriteStr(w, row.InternalPropertyKey); w.Write(",");
                w.Write("\"value\":"); WriteStr(w, row.Value); w.Write(",");
                w.Write("\"sourceNodeClass\":"); WriteStr(w, row.SourceNodeClass); w.Write(",");
                w.Write("\"sourceNodeName\":"); WriteStr(w, row.SourceNodeName); w.Write(",");
                w.Write("\"sourcePath\":"); WriteStr(w, row.SourcePath); w.Write(",");
                w.Write("\"sourceFileName\":"); WriteStr(w, row.SourceFileName); w.Write(",");
                w.Write("\"ancestorDistance\":"); w.Write(row.AncestorDistance.ToString(Inv));
                w.Write("}");
            }
            w.Write("],\"derivedUniformat\":{");
            w.Write("\"code\":"); WriteStr(w, e.UniformatCode); w.Write(",");
            w.Write("\"title\":"); WriteStr(w, e.UniformatTitle);
            w.Write(",\"source\":\"UniformatClassifier.Classify\"}}");
            w.Write(",");


            w.Write("\"properties\":{");
            if (e.Properties != null)
            {
                bool first = true;
                foreach (var kv in e.Properties)
                {
                    if (!first) w.Write(",");
                    first = false;
                    WriteStr(w, kv.Key); w.Write(":"); WriteStr(w, kv.Value);
                }
            }
            w.Write("},");

            w.Write("\"coordinateUnits\":"); WriteStr(w, e.CoordinateUnits); w.Write(",");
            w.Write("\"coordinateFrame\":\"navisworks-document\",\"spatialSource\":\"ModelItem.BoundingBox including children\",");
            w.Write("\"spatialStatus\":"); WriteStr(w, e.BoundingBox == null ? "missing" : "available"); w.Write(",");
            w.Write("\"position\":");
            if (e.BoundingBox == null) w.Write("null");
            else {
                var p = e.BoundingBox;
                w.Write("{\"x\":" + Num(p.MinX / 2 + p.MaxX / 2) + ",\"y\":" + Num(p.MinY / 2 + p.MaxY / 2) + ",\"z\":" + Num(p.MinZ / 2 + p.MaxZ / 2) + "}");
            }
            w.Write(",\"boundingBox\":");
            if (e.BoundingBox == null)
            {
                w.Write("null");
            }
            else
            {
                var b = e.BoundingBox;
                w.Write("{");
                w.Write("\"minX\":"); w.Write(Num(b.MinX)); w.Write(",");
                w.Write("\"minY\":"); w.Write(Num(b.MinY)); w.Write(",");
                w.Write("\"minZ\":"); w.Write(Num(b.MinZ)); w.Write(",");
                w.Write("\"maxX\":"); w.Write(Num(b.MaxX)); w.Write(",");
                w.Write("\"maxY\":"); w.Write(Num(b.MaxY)); w.Write(",");
                w.Write("\"maxZ\":"); w.Write(Num(b.MaxZ));
                w.Write("}");
            }
            w.Write("}");
        }

        private static readonly System.Globalization.CultureInfo Inv =
            System.Globalization.CultureInfo.InvariantCulture;

        private static string Num(double d)
        {
            if (double.IsNaN(d) || double.IsInfinity(d)) return "0";
            return d.ToString("R", Inv);
        }

        private static void WriteStr(TextWriter w, string s)
        {
            if (s == null) { w.Write("\"\""); return; }
            w.Write('"');
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': w.Write("\\\""); break;
                    case '\\': w.Write("\\\\"); break;
                    case '\b': w.Write("\\b"); break;
                    case '\f': w.Write("\\f"); break;
                    case '\n': w.Write("\\n"); break;
                    case '\r': w.Write("\\r"); break;
                    case '\t': w.Write("\\t"); break;
                    default:
                        if (c < 0x20)
                            w.Write("\\u" + ((int)c).ToString("x4", Inv));
                        else
                            w.Write(c);
                        break;
                }
            }
            w.Write('"');
        }

        private static void WriteStatus(string path, string phase, int processed, int total, string message, int percent = 0)
        {
            try
            {
                using (var w = new StreamWriter(File.Create(path), new UTF8Encoding(false)))
                {
                    w.Write("{");
                    w.Write("\"phase\":"); WriteStr(w, phase); w.Write(",");
                    w.Write("\"processed\":"); w.Write(processed.ToString(Inv)); w.Write(",");
                    w.Write("\"total\":"); w.Write(total.ToString(Inv)); w.Write(",");
                    w.Write("\"percent\":"); w.Write(percent.ToString(Inv)); w.Write(",");
                    w.Write("\"message\":"); WriteStr(w, message); w.Write(",");
                    w.Write("\"updatedUtc\":"); WriteStr(w, DateTime.UtcNow.ToString("o"));
                    w.Write("}");
                }
            }
            catch { /* status is best-effort */ }
        }
    }

    // ---- DTOs (net48, DataContract for DataContractJsonSerializer) ----

    [DataContract]
    public class ElementDto
    {
        [DataMember(Name = "id")] public string Id { get; set; }
        [DataMember(Name = "displayName")] public string DisplayName { get; set; }
        [DataMember(Name = "classDisplayName")] public string ClassDisplayName { get; set; }
        [DataMember(Name = "hasGeometry")] public bool HasGeometry { get; set; }
        [DataMember(Name = "isHidden")] public bool IsHidden { get; set; }
        [DataMember(Name = "ancestorPath")] public string AncestorPath { get; set; }
        [DataMember(Name = "coordinateUnits")] public string CoordinateUnits { get; set; }
        [DataMember(Name = "sourceFileName")] public string SourceFileName { get; set; }
        [DataMember(Name = "properties")] public Dictionary<string, string> Properties { get; set; }
        public List<ClassificationPropertyDto> ClassificationEvidence { get; set; }
        [DataMember(Name = "boundingBox")] public BBoxDto BoundingBox { get; set; }
        [DataMember(Name = "uniformatCode")] public string UniformatCode { get; set; }
        [DataMember(Name = "uniformatTitle")] public string UniformatTitle { get; set; }
        [DataMember(Name = "boqEligible")] public bool BoqEligible { get; set; }
    }

    public class ClassificationPropertyDto
    {
        public string Kind, PropertyKey, InternalPropertyKey, Value;
        public string SourceNodeClass, SourceNodeName, SourcePath, SourceFileName;
        public int AncestorDistance;
    }

    [DataContract]
    public class BBoxDto
    {
        [DataMember(Name = "minX")] public double MinX { get; set; }
        [DataMember(Name = "minY")] public double MinY { get; set; }
        [DataMember(Name = "minZ")] public double MinZ { get; set; }
        [DataMember(Name = "maxX")] public double MaxX { get; set; }
        [DataMember(Name = "maxY")] public double MaxY { get; set; }
        [DataMember(Name = "maxZ")] public double MaxZ { get; set; }
    }

    [DataContract]
    public class ModelSnapshot
    {
        [DataMember(Name = "source")] public string Source { get; set; }
        [DataMember(Name = "modelName")] public string ModelName { get; set; }
        [DataMember(Name = "coordinateUnits")] public string CoordinateUnits { get; set; }
        [DataMember(Name = "snapshotUtc")] public string SnapshotUtc { get; set; }
        [DataMember(Name = "elementCount")] public int ElementCount { get; set; }
        [DataMember(Name = "elements")] public List<ElementDto> Elements { get; set; }
    }

    [DataContract]
    public class ExportStatus
    {
        [DataMember(Name = "phase")] public string Phase { get; set; }
        [DataMember(Name = "processed")] public int Processed { get; set; }
        [DataMember(Name = "total")] public int Total { get; set; }
        [DataMember(Name = "percent")] public int Percent { get; set; }
        [DataMember(Name = "message")] public string Message { get; set; }
        [DataMember(Name = "updatedUtc")] public string UpdatedUtc { get; set; }
    }
}
