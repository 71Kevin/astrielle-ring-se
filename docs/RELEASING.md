# Release checklist

1. **Credits.** Check the credits and permissions of every file in the package, and credit every asset source in the
   README and the release notes.
2. **Version.** Set `$Version` in `build.ps1` and add a section to `CHANGELOG.md`.
3. **Build.** Run `.\build.ps1`; the package lands in `dist\` as `Astrielle Ring - <version>.zip`.
4. **Check the package.**
   - `7z t` passes on the archive.
   - The archive holds `[Tinesh] Astrielle Ring.esp`, `meshes\Tinesh\AstrielleRing` (four models) and
     `textures\Tinesh\AstrielleRing` (six textures) at the root, with no `Data` folder level and nothing else.
   - DDS headers: BC7 with full mip chains; ring textures 4096 × 2048 px, gem diffuse 2048 × 2048 px, gem normal map
     and reflection mask 256 × 256 px.
   - The plugin is ESL-flagged and its only master is `Skyrim.esm`.
   - Install the package in Mod Organizer 2 and test in game: the ring on the table in the Sleeping Giant Inn, the
     inventory description, the effects under Active Effects, the ring on the finger in third and first person, on a
     female and a male character.
5. **Release asset.** Copy the tested package to `dist\` as `Astrielle-Ring-<version>.zip` (GitHub turns spaces in
   asset names into dots) and note its SHA-256 (`Get-FileHash`).
6. **Release.** Tag `v<version>` on `main` with installation notes and the checksum:

   ```powershell
   gh release create v1.0 --target main --title "Astrielle Ring 1.0" --notes-file notes.md `
       "dist\Astrielle-Ring-1.0.zip#Astrielle Ring - 1.0"
   ```

7. **README.** Point the Downloads table at the new asset
   (`https://github.com/71Kevin/astrielle-ring-se/releases/download/v<version>/<file>`) and keep the Mod pages table up
   to date.
8. **Verify.** Download the asset from the release page and compare its SHA-256 with the tested package.
