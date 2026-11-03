using System;

namespace NavisMCPExporter
{
    /// <summary>
    /// Maps a Navisworks/Revit element to a UNIFORMAT II classification
    /// (ASTM E1557 functional element codes).
    ///
    /// The source model exposes Revit-style category names through
    /// <c>ModelItem.ClassDisplayName</c> (e.g. "Walls: Basic Wall: AR_P2_15mm",
    /// "Doors: AD1: AD1", "Floors: Floor: F2-50mm"). We derive the leading
    /// category token and match it against a rule table. Wall / door
    /// sub-classification (exterior vs interior) is refined from the family/type
    /// text when possible.
    ///
    /// This is a best-effort heuristic classifier — it never throws and always
    /// returns a result (falling back to Z1010 "Unclassified" when nothing
    /// matches) so the export pipeline is never interrupted.
    /// </summary>
    internal static class UniformatClassifier
    {
        public struct Result
        {
            public Result(string code, string title) : this()
            {
                Code = code;
                Title = title;
            }

            public string Code { get; private set; }
            public string Title { get; private set; }
        }

        private static readonly Result Unclassified = new Result("Z1010", "Unclassified");

        /// <summary>
        /// Structural / helper node classes that are NOT quantifiable BOQ items.
        /// These are tree scaffolding (category / family / type grouping nodes),
        /// geometry leaves (<c>Solid</c>), or the model container itself. They
        /// carry no quantities of their own — the real Revit instance one level
        /// up holds the Area/Volume/Length properties — so counting them would
        /// double-count. Compared against the leading category token.
        /// </summary>
        private static readonly string[] NonBoqClasses =
        {
            "solid", "type", "family", "category", "layer", "file",
            "level", "grid", "reference planes", "reference plane",
        };

        /// <summary>
        /// Decide whether an element should appear in a Bill of Quantities.
        ///
        /// Returns <c>false</c> for structural/helper nodes (see
        /// <see cref="NonBoqClasses"/>) and for spatial/datum items (rooms,
        /// areas, room separations, grids/levels) which describe space rather
        /// than constructed quantities. Everything else — the real Revit
        /// instances such as walls, floors, doors, windows — is BOQ-eligible.
        ///
        /// This is the single source of truth: the exporter uses it to skip
        /// nodes at the source, and the server exposes the same flag so no
        /// consumer has to re-derive the rule.
        /// </summary>
        public static bool IsBoqElement(string classDisplayName, string displayName)
        {
            var category = LeadingToken(classDisplayName);

            if (string.IsNullOrEmpty(category))
                return false; // no class token — grouping/helper node

            foreach (var c in NonBoqClasses)
            {
                if (category == c)
                    return false;
            }

            // Spatial / datum items: classified but not quantifiable construction.
            switch (category)
            {
                case "rooms":
                case "room":
                case "<room separation>":
                case "areas":
                case "levels":
                case "grids":
                    return false;
            }

            return true;
        }

        /// <summary>
        /// Classify an element from its category display name and (optionally)
        /// its instance display name. Matching is case-insensitive and driven by
        /// the leading category token before the first colon.
        /// </summary>
        public static Result Classify(string classDisplayName, string displayName)
        {
            var category = LeadingToken(classDisplayName);
            var haystack = ((classDisplayName ?? "") + " " + (displayName ?? "")).ToLowerInvariant();

            switch (category)
            {
                case "walls":
                case "wall":
                case "basic wall":
                    return IsExterior(haystack)
                        ? new Result("B2010", "Exterior Walls")
                        : new Result("C1010", "Partitions");

                case "wall sweeps":
                    return new Result("B2010", "Exterior Walls");

                case "curtain wall":
                case "curtain panels":
                case "curtain systems":
                    return new Result("B2020", "Exterior Windows"); // glazed enclosure

                case "windows":
                case "window":
                    return new Result("B2020", "Exterior Windows");

                case "doors":
                case "door":
                    return IsExterior(haystack)
                        ? new Result("B2030", "Exterior Doors")
                        : new Result("C1020", "Interior Doors");

                case "floors":
                case "floor":
                    return new Result("B1010", "Floor Construction");

                case "roofs":
                case "roof":
                    return new Result("B1020", "Roof Construction");

                case "ceilings":
                case "ceiling":
                    return new Result("C3030", "Ceiling Finishes");

                case "stairs":
                case "stair":
                case "runs":
                case "landings":
                case "treads/risers":
                    return new Result("C2010", "Stair Construction");

                case "railings":
                case "railing":
                case "balusters":
                    return new Result("C2020", "Stair Railings & Balustrades");

                case "columns":
                case "structural columns":
                case "structural column":
                    // Vertical superstructure. Kept under the B1010 family but
                    // given a distinct sub-code so BOQ separates columns from
                    // beams and slabs (they price very differently).
                    return new Result("B1011", "Structural Columns");

                case "structural framing":
                case "beams":
                case "beam":
                case "framing":
                    return new Result("B1012", "Structural Framing (Beams)");

                case "structural foundations":
                case "foundation":
                case "footings":
                    return new Result("A1010", "Standard Foundations");

                case "rooms":
                case "room":
                case "<room separation>":
                case "areas":
                    return new Result("Z1020", "Spatial / Room");

                case "levels":
                case "level":
                case "grids":
                case "grid":
                case "reference planes":
                    return new Result("Z1030", "Datum / Reference");

                case "casework":
                case "furniture":
                case "furniture systems":
                    return new Result("E2010", "Fixed Furnishings");

                case "plumbing fixtures":
                    return new Result("D2010", "Plumbing Fixtures");

                case "mechanical equipment":
                    return new Result("D3050", "Terminal & Package Units");

                case "ducts":
                case "duct fittings":
                    return new Result("D3040", "Distribution Systems (HVAC)");

                case "pipes":
                case "pipe fittings":
                    return new Result("D2090", "Other Plumbing Systems");

                case "electrical equipment":
                case "electrical fixtures":
                case "lighting fixtures":
                    return new Result("D5020", "Lighting & Branch Wiring");

                case "signage":
                    return new Result("E2010", "Fixed Furnishings");

                case "generic models":
                case "generic model":
                case "mass":
                    return ClassifyGeneric(haystack);

                case "solid":
                    return Unclassified;
            }

            // Fall through: try keyword hints on the whole string.
            return ClassifyByKeyword(haystack);
        }

        private static Result ClassifyGeneric(string haystack)
        {
            if (haystack.Contains("canopy") || haystack.Contains("facade") || haystack.Contains("roof top"))
                return new Result("B2010", "Exterior Walls");
            if (haystack.Contains("logo") || haystack.Contains("signage") || haystack.Contains("ป้าย"))
                return new Result("E2010", "Fixed Furnishings");
            return Unclassified;
        }

        private static Result ClassifyByKeyword(string haystack)
        {
            if (haystack.Length == 0) return Unclassified;

            if (haystack.Contains("facade") || haystack.Contains("curtain") || haystack.Contains("canopy"))
                return new Result("B2010", "Exterior Walls");
            if (haystack.Contains("window") || haystack.Contains("glazing"))
                return new Result("B2020", "Exterior Windows");
            if (haystack.Contains("door"))
                return new Result("C1020", "Interior Doors");
            if (haystack.Contains("floor") || haystack.Contains("slab"))
                return new Result("B1010", "Floor Construction");
            if (haystack.Contains("roof"))
                return new Result("B1020", "Roof Construction");
            if (haystack.Contains("ceiling"))
                return new Result("C3030", "Ceiling Finishes");
            if (haystack.Contains("stair") || haystack.Contains("tread") || haystack.Contains("riser"))
                return new Result("C2010", "Stair Construction");
            if (haystack.Contains("railing") || haystack.Contains("baluster") || haystack.Contains("balustrade"))
                return new Result("C2020", "Stair Railings & Balustrades");
            // Structural keyword hints (ST models) — check before the generic
            // wall/partition catch so beams/columns aren't mislabelled.
            if (haystack.Contains("footing") || haystack.Contains("foundation") || haystack.Contains("pile") || haystack.Contains("pilecap"))
                return new Result("A1010", "Standard Foundations");
            if (haystack.Contains("column"))
                return new Result("B1011", "Structural Columns");
            if (haystack.Contains("beam") || haystack.Contains("framing") || haystack.Contains("girder") || haystack.Contains("truss"))
                return new Result("B1012", "Structural Framing (Beams)");
            if (haystack.Contains("wall") || haystack.Contains("partition"))
                return new Result("C1010", "Partitions");

            return Unclassified;
        }

        /// <summary>Exterior enclosure hints used to split walls/doors.</summary>
        private static bool IsExterior(string haystack)
        {
            return haystack.Contains("facade") ||
                   haystack.Contains("curtain") ||
                   haystack.Contains("exterior") ||
                   haystack.Contains("ext_") ||
                   haystack.Contains("_ext") ||
                   haystack.Contains("brick") ||   // AR_BRICK_* are exterior/masonry envelope in this model
                   haystack.Contains("q-con") ||    // Q-CON AAC block — envelope masonry
                   haystack.Contains("canopy") ||
                   haystack.Contains("entrance");
        }

        /// <summary>Return the lower-cased category token before the first colon.</summary>
        private static string LeadingToken(string classDisplayName)
        {
            if (string.IsNullOrWhiteSpace(classDisplayName)) return "";
            var idx = classDisplayName.IndexOf(':');
            var token = idx >= 0 ? classDisplayName.Substring(0, idx) : classDisplayName;
            return token.Trim().ToLowerInvariant();
        }
    }
}
