# Keeping this profile alive

`README.md` is the public profile. Edit the introduction and project links there. The two `REPO-PULSE` markers surround the section maintained by `scripts/update_profile.py`; keep one copy of each marker.

The workflow `.github/workflows/refresh-profile.yml` checks public, non-fork repositories owned by `yihuanghuan` daily, around 09:23 China time. It also runs when the updater, tests, workflow, or README changes, and can be run manually from the Actions tab. Scheduled runs can be delayed by GitHub. Public repositories with no activity for 60 days can have their scheduled workflows disabled.

Stars here mean stars received by these repositories, not repositories the account has starred. The profile repository and forks are excluded. The change column compares repositories present in both the current and previous successful check; new and removed repositories are not treated as star/unstar events. Release entries come from GitHub Releases, with prereleases labeled. Tags and ordinary pushes are not releases.

`data/repo-pulse.json` stores the latest public snapshot. `data/star-history.json` keeps one successful observation per day, up to 180 days. History begins with the first check; it does not estimate earlier star counts. API errors fail the run and leave the published data untouched.

The contribution animation uses [Platane/snk](https://github.com/Platane/snk), pinned to its v3.5.0 commit. Colors can be changed in the `outputs` input. All actions are pinned to full commit SHAs. The generation job has read-only permissions; only the separate publishing job can write this profile repository. No personal access token or extra secret is required.

The doodle is a fictional cat-and-robot scene. It does not depict a research result. The PNG is used when the visitor prefers reduced motion.

Design references: [Sindre Sorhus](https://github.com/sindresorhus/sindresorhus), [Cassidy Williams](https://github.com/cassidoo/cassidoo), and [Simon Willison's self-updating profile](https://github.com/simonw/simonw). These profiles informed the small GIF, personal voice, and self-updating releases section; their artwork and prose were not copied.

The colored handwritten labels are local PNG assets with transparent backgrounds and separate dark variants. They use Segoe Print and simple drawn icons; no external badge service is required. Keep their alt text descriptive. The interests section reflects the owner's stated music, travel, and investing preferences.
