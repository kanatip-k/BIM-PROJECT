using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text.RegularExpressions;
using Autodesk.Navisworks.Api;
using Autodesk.Navisworks.Api.Plugins;

namespace Case2Inventory {
[Plugin("Case2PropertyInventory", "KNTI", DisplayName="Read-only NWC Property Inventory")]
public class Inspector : AddInPlugin {
    public override int Execute(params string[] args) {
        if(args.Length==0) return 10;
        try {
            var doc=Application.ActiveDocument;
            var result=new Inventory { ModelFile=doc.CurrentFileName, Units=doc.Units.ToString(),
                SnapshotUtc=DateTime.UtcNow.ToString("o"), Keys=new List<KeyInventory>() };
            var keys=new Dictionary<string,KeyInventory>();
            foreach(Model model in doc.Models) {
                var stack=new Stack<ModelItem>(); stack.Push(model.RootItem);
                while(stack.Count>0) {
                    var item=stack.Pop(); result.TotalNodes++;
                    foreach(ModelItem child in item.Children) stack.Push(child);
                    foreach(PropertyCategory category in item.PropertyCategories) {
                        foreach(DataProperty property in category.Properties) {
                            string key=(category.DisplayName??category.Name??"")+"."+(property.DisplayName??property.Name??"");
                            string internalKey=(category.Name??"")+"."+(property.Name??"");
                            string lookup=key+"\u001f"+internalKey;
                            KeyInventory entry;
                            if(!keys.TryGetValue(lookup,out entry)) {
                                entry=new KeyInventory { DisplayKey=key, InternalKey=internalKey, Values=new List<ValueInventory>(),
                                    Candidate=IsCandidate(key+" "+internalKey) };
                                keys.Add(lookup,entry); result.Keys.Add(entry);
                            }
                            entry.NodeOccurrences++;
                            string value="";
                            try { value=property.Value.ToDisplayString(); }
                            catch { try { value=property.Value.ToString(); } catch {} }
                            if(!String.IsNullOrWhiteSpace(value)) entry.NonEmptyOccurrences++;
                            if(!entry.Candidate) continue;
                            ValueInventory row=entry.Values.Find(v=>v.Value==value);
                            if(row==null) { row=new ValueInventory { Value=value, Examples=new List<NodeEvidence>() }; entry.Values.Add(row); }
                            row.Count++;
                            if(row.Examples.Count<5) {
                                var names=new List<string>(); var current=item;
                                while(current!=null) { names.Insert(0,current.DisplayName??""); current=current.Parent; }
                                row.Examples.Add(new NodeEvidence { Id=item.InstanceGuid.ToString(), DisplayName=item.DisplayName,
                                    ClassDisplayName=item.ClassDisplayName, AncestorPath=String.Join(" > ",names.ToArray()), HasGeometry=item.HasGeometry });
                            }
                        }
                    }
                }
            }
            result.Keys.Sort((a,b)=>String.CompareOrdinal(a.DisplayKey,b.DisplayKey));
            var serializer=new DataContractJsonSerializer(typeof(Inventory));
            using(var stream=File.Create(args[0])) serializer.WriteObject(stream,result);
            return 0;
        } catch(Exception ex) { File.WriteAllText(args[0]+".error.txt",ex.ToString()); return 99; }
    }
    private static bool IsCandidate(string key) {
        string normal=Regex.Replace(key.ToLowerInvariant(),"[^a-z0-9]","");
        foreach(string token in new[]{"masterformat","omniclass","omniformat","uniformat","assemblycode","assemblydescription","classification","keynote"})
            if(normal.Contains(token)) return true;
        return false;
    }
}
[DataContract] public class Inventory {
[DataMember] public string ModelFile;
[DataMember] public string Units;
[DataMember] public string SnapshotUtc;
[DataMember] public int TotalNodes;
[DataMember] public List<KeyInventory> Keys;
}
[DataContract] public class KeyInventory {
[DataMember] public string DisplayKey;
[DataMember] public string InternalKey;
[DataMember] public int NodeOccurrences;
[DataMember] public int NonEmptyOccurrences;
[DataMember] public bool Candidate;
[DataMember] public List<ValueInventory> Values;
}
[DataContract] public class ValueInventory {
[DataMember] public string Value;
[DataMember] public int Count;
[DataMember] public List<NodeEvidence> Examples;
}
[DataContract] public class NodeEvidence {
[DataMember] public string Id;
[DataMember] public string DisplayName;
[DataMember] public string ClassDisplayName;
[DataMember] public string AncestorPath;
[DataMember] public bool HasGeometry;
}
}