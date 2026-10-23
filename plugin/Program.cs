using System.Text.Json;
using Mutagen.Bethesda;
using Mutagen.Bethesda.Plugins;
using Mutagen.Bethesda.Plugins.Records;
using Mutagen.Bethesda.Skyrim;
using Noggog;

var skyrimPath = args[0];
var outDir = args[1];
using var meshReport = JsonDocument.Parse(File.ReadAllText(args[2]));
var version = args[3];

const SkyrimRelease release = SkyrimRelease.SkyrimSE;
const string meshDir = @"Tinesh\AstrielleRing\";
var modKey = ModKey.FromFileName("[Tinesh] Astrielle Ring.esp");
var skyrimKey = ModKey.FromFileName("Skyrim.esm");
FormKey Mine(uint id) => new(modKey, id);
FormKey Vanilla(uint id) => new(skyrimKey, id);

using var skyrim = SkyrimMod.CreateFromBinaryOverlay(skyrimPath, release);
var cache = skyrim.ToImmutableLinkCache();
T Find<T>(IEnumerable<T> records, string editorId) where T : IMajorRecordGetter =>
    records.FirstOrDefault(r => r.EditorID == editorId) ?? throw new InvalidOperationException($"{editorId} not found in Skyrim.esm");
IFormLinkGetter<IKeywordGetter> Kw(string editorId) => Find(skyrim.Keywords, editorId).ToLinkGetter();

var mod = new SkyrimMod(modKey, release);
mod.ModHeader.Flags |= SkyrimModHeader.HeaderFlag.Small;
mod.ModHeader.Author = "Tinesh";
mod.ModHeader.Description = $"Astrielle Ring {version}: one star-set ring that gathers regeneration, faster learning and the everyday bonuses of a well-equipped adventurer. Lies on a table in the Sleeping Giant Inn, Riverwood.";

MagicEffect Constant(uint id, string editorId, string template, string name, string description)
{
    var e = Find(skyrim.MagicEffects, template).Duplicate(Mine(id));
    e.EditorID = editorId;
    e.Name = name;
    e.Description = description;
    e.CastType = CastType.ConstantEffect;
    e.TargetType = TargetType.Self;
    e.Flags = (e.Flags | MagicEffect.Flag.NoDuration | MagicEffect.Flag.NoArea | MagicEffect.Flag.Recover) & ~MagicEffect.Flag.PowerAffectsDuration;
    e.Keywords?.Clear();
    e.HitShader.Clear();
    e.Sounds?.Clear();
    if (e.Archetype is MagicEffectPeakValueModArchetype peak)
        peak.Association.Clear();
    mod.MagicEffects.Add(e);
    return e;
}

MagicEffect PerkCarrier(uint id, string editorId, string name, string description, Perk perk)
{
    var e = new MagicEffect(Mine(id), release)
    {
        EditorID = editorId,
        Name = name,
        Description = description,
        CastType = CastType.ConstantEffect,
        TargetType = TargetType.Self,
        Flags = MagicEffect.Flag.Recover | MagicEffect.Flag.NoDuration | MagicEffect.Flag.NoMagnitude | MagicEffect.Flag.NoArea,
        Archetype = new MagicEffectArchetype(MagicEffectArchetype.TypeEnum.Script),
        CastingSoundLevel = SoundLevel.Silent,
    };
    e.PerkToApply.SetTo(perk.FormKey);
    e.MenuDisplayObject.SetTo(Vanilla(0x0435A5));
    mod.MagicEffects.Add(e);
    return e;
}

Perk HiddenPerk(uint id, string editorId, string name, APerkEntryPointEffect entry)
{
    var p = new Perk(Mine(id), release)
    {
        EditorID = editorId,
        Name = name,
        Description = "",
        Playable = false,
        Hidden = true,
        NumRanks = 1,
    };
    p.Effects.Add(entry);
    mod.Perks.Add(p);
    return p;
}

var learningPerk = HiddenPerk(0x803, "AstrielleRingLearningPerk", "Astrielle's Learning", new PerkEntryPointModifyValue
{
    EntryPoint = APerkEntryPointEffect.EntryType.ModSkillUse,
    PerkConditionTabCount = 1,
    Modification = PerkEntryPointModifyValue.ModificationType.Multiply,
    Value = 1.3f,
});
var cushionPerk = HiddenPerk(0x804, "AstrielleRingCushionPerk", "Astrielle's Cushion", new PerkEntryPointModifyValue
{
    EntryPoint = APerkEntryPointEffect.EntryType.ModFallingDamage,
    PerkConditionTabCount = 1,
    Modification = PerkEntryPointModifyValue.ModificationType.Multiply,
    Value = 0f,
});

var learning = PerkCarrier(0x805, "AstrielleRingLearning", "Astrielle's Learning", "Skills improve 30% faster.", learningPerk);
var cushion = PerkCarrier(0x806, "AstrielleRingCushion", "Cushioned", "Negates all falling damage.", cushionPerk);

var speed = Constant(0x807, "AstrielleRingSpeed", "EnchFortifyCarryConstantSelf", "Fleet Foot", "You move <mag>% faster.");
speed.Archetype.ActorValue = ActorValue.SpeedMult;

var merchant = Constant(0x808, "AstrielleRingMerchant", "PerkMerchantEffect", "Merchant", "Sell any type of item to any kind of merchant.");
merchant.Flags = (merchant.Flags | MagicEffect.Flag.NoMagnitude) & ~MagicEffect.Flag.HideInUI;
merchant.MenuDisplayObject.SetTo(Vanilla(0x0435A5));

var recharge = Constant(0x809, "AstrielleRingRecharge", "EnchFortifyCarryConstantSelf", "Recharge Weapons",
    "Recharges equipped weapons <mag> points per second, up to the charge they had when equipped.");
recharge.Archetype = new MagicEffectArchetype(MagicEffectArchetype.TypeEnum.DualValueModifier) { ActorValue = ActorValue.LeftItemCharge };
recharge.SecondActorValue = ActorValue.RightItemCharge;
recharge.SecondActorValueWeight = 1;
recharge.Flags &= ~MagicEffect.Flag.Recover;

var shouts = Find(skyrim.MagicEffects, "EnchFortifyShoutTimerConstantSelf").Duplicate(Mine(0x80A));
shouts.EditorID = "AstrielleRingShouts";
shouts.Description = "Time between shouts is reduced 20%.";
mod.MagicEffects.Add(shouts);

var enchanting = Constant(0x80B, "AstrielleRingEnchanting", "AlchFortifyEnchanting", "Fortify Enchanting", "Items are enchanted <mag>% stronger.");

var schools = new[]
{
    (Id: 0x80Cu, School: "Alteration", Text: "Alteration spells last <mag>% longer."),
    (Id: 0x80Du, School: "Conjuration", Text: "Conjurations last <mag>% longer."),
    (Id: 0x80Eu, School: "Destruction", Text: "Destruction spells are <mag>% stronger."),
    (Id: 0x80Fu, School: "Illusion", Text: "Illusion spells are <mag>% stronger."),
    (Id: 0x810u, School: "Restoration", Text: "Restoration spells are <mag>% stronger."),
};
var schoolPower = schools.Select(s => Constant(s.Id, $"AstrielleRingEmpower{s.School}", $"AlchFortify{s.School}", $"Empower {s.School}", s.Text)).ToArray();

var effects = new List<(FormKey Effect, float Magnitude)>
{
    (Vanilla(0x07A0F8), 100), (Vanilla(0x07A0FD), 100), (Vanilla(0x07A105), 100),
    (learning.FormKey, 0),
    (Vanilla(0x07A0FF), 40), (Vanilla(0x07A0FB), 40),
    (Vanilla(0x07A106), 30), (Vanilla(0x07A0FE), 30), (Vanilla(0x07A0F3), 30),
    (Vanilla(0x07A0F2), 25), (Vanilla(0x07A0F5), 25), (Vanilla(0x07A0F6), 25), (Vanilla(0x07A0FA), 25), (Vanilla(0x07A101), 25),
};
effects.AddRange(schoolPower.Select(e => (e.FormKey, 25f)));
effects.AddRange(new (FormKey, float)[]
{
    (Vanilla(0x07A103), 30), (Vanilla(0x0D6933), 30), (Vanilla(0x07A104), 25), (merchant.FormKey, 1),
    (Vanilla(0x08B65C), 25), (Vanilla(0x07A102), 25), (enchanting.FormKey, 25),
    (Vanilla(0x0B7A35), 25),
    (speed.FormKey, 15), (Vanilla(0x07A0F4), 100),
    (cushion.FormKey, 0), (recharge.FormKey, 15), (shouts.FormKey, 0.2f),
});

var enchantment = new ObjectEffect(Mine(0x802), release)
{
    EditorID = "AstrielleRingEnch",
    Name = "Astrielle's Grace",
    CastType = CastType.ConstantEffect,
    TargetType = TargetType.Self,
    EnchantType = ObjectEffect.EnchantTypeEnum.Enchantment,
    Flags = ObjectEffect.Flag.NoAutoCalc,
    EnchantmentCost = 0,
    EnchantmentAmount = 0,
};
foreach (var (effect, magnitude) in effects)
    enchantment.Effects.Add(new Effect { BaseEffect = new FormLinkNullable<IMagicEffectGetter>(effect), Data = new EffectData { Magnitude = magnitude } });
mod.ObjectEffects.Add(enchantment);

var races = new uint[]
{
    0x013740, 0x08883A, 0x013741, 0x08883C, 0x097A3D, 0x013742, 0x08883D, 0x0F71DC, 0x000D53, 0x067CD8, 0x0A82BA,
    0x013743, 0x088840, 0x013744, 0x088844, 0x013745, 0x088845, 0x10760A, 0x013746, 0x088794, 0x013747, 0x0A82B9,
    0x013748, 0x088846, 0x013749, 0x088884,
};
var vanillaAddon = Find(skyrim.ArmorAddons, "RingGoldSappireAA");
var addon = vanillaAddon.Duplicate(Mine(0x801));
addon.EditorID = "AstrielleRingAA";
addon.WorldModel = new GenderedItem<Model?>(new Model { File = meshDir + "AstrielleRing_1.nif" }, new Model { File = meshDir + "AstrielleRingF_1.nif" });
addon.WeightSliderEnabled = new GenderedItem<bool>(true, false);
addon.Race.SetTo(Find(skyrim.Races, "DefaultRace").FormKey);
addon.AdditionalRaces.Clear();
foreach (var r in races)
    addon.AdditionalRaces.Add(new FormLink<IRaceGetter>(Vanilla(r)));
mod.ArmorAddons.Add(addon);

var o = meshReport.RootElement.GetProperty("ground").GetProperty("bounds").GetProperty("obnd").EnumerateArray().Select(v => (short)v.GetInt32()).ToArray();
var ring = Find(skyrim.Armors, "JewelryRingGoldSapphire").Duplicate(Mine(0x800));
ring.EditorID = "AstrielleRing";
ring.Name = "Astrielle Ring";
ring.Description = "An heirloom from Astrielle's grandfather. Its star ruby burns like her eyes. Guard it well.";
ring.WorldModel = new GenderedItem<ArmorModel?>(new ArmorModel { Model = new Model { File = meshDir + "AstrielleRingGO.nif" } }, null);
ring.ObjectBounds = new ObjectBounds { First = new P3Int16(o[0], o[1], o[2]), Second = new P3Int16(o[3], o[4], o[5]) };
ring.ObjectEffect.SetTo(enchantment.FormKey);
ring.Value = 3000;
ring.Armature.Clear();
ring.Armature.Add(addon.ToLink());
ring.Keywords!.Add(Kw("MagicDisallowEnchanting"));
mod.Armors.Add(ring);

var inn = cache.ResolveContext<ICell, ICellGetter>(Vanilla(0x0133C6));
var cell = inn.GetOrAddAsOverride(mod);
var placed = new PlacedObject(Mine(0x811), release)
{
    Placement = new Placement { Position = new P3Float(-951.4f, -869.7f, 60.06f), Rotation = new P3Float(0, 0, 0.6f) },
};
placed.Base.SetTo(ring.FormKey);
placed.Owner.SetTo(Find(skyrim.Factions, "PlayerFaction").FormKey);
cell.Temporary.Add(placed);

mod.ModHeader.Stats.NextFormID = 0x812;

Directory.CreateDirectory(outDir);
var outPath = Path.Combine(outDir, modKey.FileName);
mod.BeginWrite.ToPath(outPath).WithNoLoadOrder().Write();
Console.WriteLine($"WROTE {outPath} ({new FileInfo(outPath).Length} bytes)");

using var back = SkyrimMod.CreateFromBinaryOverlay(outPath, release);
Console.WriteLine($"HEADER ESL={back.ModHeader.Flags.HasFlag(SkyrimModHeader.HeaderFlag.Small)} records={back.ModHeader.Stats.NumRecords} next={back.ModHeader.Stats.NextFormID:X} masters={string.Join(",", back.ModHeader.MasterReferences.Select(m => m.Master.FileName))}");
foreach (var r in back.EnumerateMajorRecords())
    Console.WriteLine($"  {r.Registration.Name} {r.FormKey} {r.EditorID}");
var ench = back.ObjectEffects.Single();
foreach (var e in ench.Effects)
{
    var name = cache.TryResolve<IMagicEffectGetter>(e.BaseEffect.FormKey, out var v) ? v.EditorID : back.MagicEffects.Single(m => m.FormKey == e.BaseEffect.FormKey).EditorID;
    Console.WriteLine($"  effect {e.BaseEffect.FormKey} {name} mag={e.Data?.Magnitude}");
}
var innBack = back.EnumerateMajorRecords<ICellGetter>().Single();
Console.WriteLine($"cell {innBack.EditorID} temporary={innBack.Temporary.Count} persistent={innBack.Persistent.Count} owner={innBack.Owner.FormKey} lighting={innBack.LightingTemplate.FormKey}");
