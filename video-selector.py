#!/usr/bin/env python3
import argparse
import os
import random
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
import xml.etree.ElementTree as ET

INPUT_PLAYLIST = "alla bluey.xspf"
OUTPUT_PLAYLIST = "valda delar.xspf"

XSPF_NS = "http://xspf.org/ns/0/"
VLC_NS = "http://www.videolan.org/vlc/playlist/ns/0/"
NS = {"xspf": XSPF_NS, "vlc": VLC_NS}

ET.register_namespace("", XSPF_NS)
ET.register_namespace("vlc", VLC_NS)


def ask_episode_count(default: int, maximum: int) -> int:
    result = {"value": None}

    root = tk.Tk()
    root.title("Bluey-väljare")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=16, pady=16)
    frame.pack()

    tk.Label(frame, text=f"Välj antal avsnitt (1-{maximum}):").pack(anchor="w")

    spinbox = tk.Spinbox(frame, from_=1, to=maximum, width=8)
    spinbox.delete(0, "end")
    spinbox.insert(0, str(default))
    spinbox.pack(anchor="w", pady=(6, 12))
    spinbox.focus_set()

    def submit() -> None:
        try:
            value = int(spinbox.get())
        except ValueError:
            messagebox.showerror("Fel", "Ange ett heltal.")
            return

        if not 1 <= value <= maximum:
            messagebox.showerror("Fel", f"Antalet måste vara mellan 1 och {maximum}.")
            return

        result["value"] = value
        root.destroy()

    def cancel() -> None:
        root.destroy()

    buttons = tk.Frame(frame)
    buttons.pack(anchor="e")
    tk.Button(buttons, text="Starta", command=submit).pack(side="left", padx=(0, 8))
    tk.Button(buttons, text="Avbryt", command=cancel).pack(side="left")

    root.bind("<Return>", lambda event: submit())
    root.bind("<Escape>", lambda event: cancel())
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()

    if result["value"] is None:
        raise SystemExit("Avbrutet.")

    return result["value"]


def load_tracks(root: ET.Element):
    tracklist = root.find("xspf:trackList", NS)
    if tracklist is None:
        raise ValueError("Kunde inte hitta <trackList> i spellistan.")

    tracks = tracklist.findall("xspf:track", NS)
    if not tracks:
        raise ValueError("Spellistan innehåller inga spår.")

    return tracklist, tracks


def choose_tracks(tracks: list[ET.Element], count: int) -> list[ET.Element]:
    if count > len(tracks):
        raise ValueError(
            f"Du kan inte välja fler avsnitt ({count}) än spellistan innehåller ({len(tracks)})."
        )

    indices = random.sample(range(len(tracks)), count)
    random.shuffle(indices)
    return [tracks[i] for i in indices]


def rebuild_playlist(root: ET.Element, selected_tracks: list[ET.Element]) -> None:
    tracklist, _ = load_tracks(root)

    for child in list(tracklist):
        tracklist.remove(child)

    for new_id, track in enumerate(selected_tracks):
        extension = track.find("xspf:extension", NS)
        if extension is None:
            extension = ET.SubElement(
                track,
                f"{{{XSPF_NS}}}extension",
                {"application": "http://www.videolan.org/vlc/playlist/0"},
            )

        vlc_id = extension.find("vlc:id", NS)
        if vlc_id is None:
            vlc_id = ET.SubElement(extension, f"{{{VLC_NS}}}id")
        vlc_id.text = str(new_id)

        tracklist.append(track)

    playlist_extension = None
    for ext in root.findall("xspf:extension", NS):
        if ext.get("application") == "http://www.videolan.org/vlc/playlist/0":
            playlist_extension = ext
            break

    if playlist_extension is None:
        playlist_extension = ET.SubElement(
            root,
            f"{{{XSPF_NS}}}extension",
            {"application": "http://www.videolan.org/vlc/playlist/0"},
        )

    for child in list(playlist_extension):
        playlist_extension.remove(child)

    for i in range(len(selected_tracks)):
        ET.SubElement(playlist_extension, f"{{{VLC_NS}}}item", {"tid": str(i)})


def indent_xml(elem: ET.Element, level: int = 0) -> None:
    indent = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "\t"
        for child in elem:
            indent_xml(child, level + 1)
        if not elem[-1].tail or not elem[-1].tail.strip():
            elem[-1].tail = indent
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = indent


def save_playlist(tree: ET.ElementTree, output_path: str) -> None:
    indent_xml(tree.getroot())
    tree.write(output_path, encoding="UTF-8", xml_declaration=True)


def start_vlc(playlist_path: str) -> None:
    vlc_path = shutil.which("vlc")
    if vlc_path is None:
        raise FileNotFoundError(
            "Kunde inte hitta VLC i PATH. Installera VLC eller lägg 'vlc' i PATH."
        )

    subprocess.Popen([vlc_path, playlist_path])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Välj slumpmässiga Bluey-avsnitt från en VLC/XSPF-spellista."
    )
    parser.add_argument(
        "count",
        nargs="?",
        type=int,
        help="Antal avsnitt att välja. Om utelämnat visas ett enkelt GUI.",
    )
    parser.add_argument(
        "--default",
        type=int,
        default=3,
        help="Förvalt antal i GUI om inget positionsargument anges (standard: 3).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.default < 1:
        print("Fel: --default måste vara minst 1.", file=sys.stderr)
        return 1

    if not os.path.exists(INPUT_PLAYLIST):
        print(f"Fel: Hittar inte '{INPUT_PLAYLIST}' i aktuell katalog.", file=sys.stderr)
        return 1

    try:
        tree = ET.parse(INPUT_PLAYLIST)
        root = tree.getroot()
        _, tracks = load_tracks(root)
        total_tracks = len(tracks)

        if args.count is None:
            count = ask_episode_count(min(args.default, total_tracks), total_tracks)
        else:
            count = args.count

        if count < 1:
            raise ValueError("Antalet avsnitt måste vara minst 1.")

        selected_tracks = choose_tracks(tracks, count)
        rebuild_playlist(root, selected_tracks)
        save_playlist(tree, OUTPUT_PLAYLIST)
        start_vlc(OUTPUT_PLAYLIST)

        print(f"Skapade '{OUTPUT_PLAYLIST}' med {count} slumpade avsnitt och startade VLC.")
        return 0

    except Exception as exc:
        print(f"Fel: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
