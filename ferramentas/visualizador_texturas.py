import csv
import json
import math
import os
import random
import struct
import subprocess
import tkinter as tk
import zlib
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


# texc.exe: tex_codec 1.8.0, commit ae0d500b7ac52378f18c309e61f3d782637f3b1d.
projectDir = Path(__file__).resolve().parent
dumpDir = Path(".")
headerPath = projectDir / "inventario_cabecalhos_g1t_20261102" / "texturas_cabecalhos.csv"
resourcePath = projectDir / "inventario_registros_g1t_pokopia.csv"
gradePath = projectDir / "grade_A_corrigida_20261102" / "grade_A_mapeamento.csv"
texcPath = projectDir / "tools" / "texc" / "texc.exe"
cacheDir = projectDir / ".cache" / "visualizador_texturas"
thumbDir = cacheDir / "miniaturas"
statePath = projectDir / "classificacoes_texturas.json"
formatNames = {"0x62": "BC3", "0x66": "BC7"}
statuses = {"traduzir", "ignorar", "revisar_depois"}
pageSize = 100
statusLabels = {
    "traduzir": "Traduzir",
    "ignorar": "Ignorar",
    "revisar_depois": "Revisar depois",
}


def readCsv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def isSingleSlice(row):
    if row["mips"] != "1":
        return True
    blocksWide = max(1, math.ceil(int(row["width"]) / 4))
    blocksHigh = max(1, math.ceil(int(row["height"]) / 4))
    return int(row["payloadSize"]) == blocksWide * blocksHigh * 16


def loadCatalog():
    headers = readCsv(headerPath)
    resources = {row["resourceId"].lower(): row for row in readCsv(resourcePath)}
    headersById = {(row["resourceId"].lower(), row["texIndex"]): row for row in headers}
    oldRows = readCsv(gradePath)
    chosen = {formatId: [] for formatId in formatNames}

    for oldRow in oldRows:
        if oldRow["grade"] != "A":
            continue
        formatId = oldRow["formatId"].lower()
        if formatId not in chosen:
            continue
        header = headersById[(oldRow["resourceId"].lower(), oldRow["texIndex"])]
        if header["parseStatus"] == "ok" and header["isArray"].lower() != "true" and isSingleSlice(header):
            chosen[formatId].append(header)

    rng = random.Random(20261102)
    candidatesByFormat = {}
    for formatId in chosen:
        candidates = [
            row for row in headers
            if row["platform"].lower() == "0x18"
            and row["formatId"].lower() == formatId
            and row["parseStatus"] == "ok"
            and row["isArray"].lower() != "true"
            and row["isCube"].lower() != "true"
            and row["isDoubleHeight"].lower() != "true"
            and isSingleSlice(row)
        ]
        candidates.sort(key=lambda row: (row["mips"] != "1", int(row["resourceId"], 0), int(row["texIndex"])))
        existing = {(row["resourceId"].lower(), row["texIndex"]) for row in chosen[formatId]}
        candidates = [row for row in candidates if (row["resourceId"].lower(), row["texIndex"]) not in existing]
        needed = max(0, 100 - len(chosen[formatId]))
        singleMip = [row for row in candidates if row["mips"] == "1"]
        otherMips = [row for row in candidates if row["mips"] != "1"]
        if len(candidates) < needed:
            raise ValueError(f"Há apenas {len(candidates) + len(chosen[formatId])} entradas {formatId} elegíveis.")
        if len(singleMip) >= needed:
            chosen[formatId].extend(rng.sample(singleMip, needed))
        else:
            chosen[formatId].extend(singleMip)
            chosen[formatId].extend(rng.sample(otherMips, needed - len(singleMip)))
        candidatesByFormat[formatId] = candidates

    moreRng = random.Random(20261103)
    for formatId in chosen:
        existing = {(row["resourceId"].lower(), row["texIndex"]) for row in chosen[formatId]}
        candidates = [row for row in candidatesByFormat[formatId] if (row["resourceId"].lower(), row["texIndex"]) not in existing]
        singleMip = [row for row in candidates if row["mips"] == "1"]
        otherMips = [row for row in candidates if row["mips"] != "1"]
        pool = singleMip if len(singleMip) >= 500 else singleMip + otherMips
        if len(pool) < 500:
            raise ValueError(f"Há apenas {len(pool)} entradas adicionais {formatId} elegíveis.")
        chosen[formatId].extend(moreRng.sample(pool, 500))

    selectedRows = [row for formatId in formatNames for row in chosen[formatId]]
    selectedIds = {(row["resourceId"].lower(), row["texIndex"]) for row in selectedRows}
    # O payload Switch 2 pode incluir padding de tiling mesmo com uma mip.
    allRows = sorted(
        (
            row for row in headers
            if row["platform"].lower() == "0x18"
            and row["formatId"].lower() in formatNames
            and row["mips"] == "1"
            and row["parseStatus"] == "ok"
            and row["isArray"].lower() != "true"
            and row["isCube"].lower() != "true"
            and row["isDoubleHeight"].lower() != "true"
        ),
        key=lambda row: (row["resourceId"].lower(), int(row["texIndex"])),
    )
    for row in allRows:
        key = (row["resourceId"].lower(), row["texIndex"])
        if key not in selectedIds:
            selectedRows.append(row)
            selectedIds.add(key)

    selected = []
    for row in selectedRows:
        resource = resources.get(row["resourceId"].lower())
        if not resource or resource["validationStatus"] != "ok":
            raise ValueError(f"FDATA indisponível para {row['resourceId']}.")
        width, height = int(row["width"]), int(row["height"])
        formatId = row["formatId"].lower()
        selected.append({
            "id": f"{row['resourceId'].lower()}:{row['texIndex']}",
            "resourceId": row["resourceId"].lower(),
            "texIndex": int(row["texIndex"]),
            "formatId": formatId,
            "format": formatNames[formatId],
            "width": width,
            "height": height,
            "mips": int(row["mips"]),
            "payloadOffset": int(row["payloadOffset"], 0),
            "payloadSize": int(row["payloadSize"]),
            "fdataPath": resource["fdataPath"],
            "fdataOffset": int(resource["offsetBytes"], 0),
            "storedSize": int(resource["storedSize"]),
            "rawSize": int(resource["uncompressedSizeFdata"]),
            "ktid": int(resource["ktid"], 0),
            "entryType": int(resource["entryType"], 0),
            "flags": int(resource["fdataFlags"], 0),
        })

    if len(selected) != len({row["id"] for row in selected}):
        raise ValueError("O catálogo contém IDs de textura duplicados.")
    for number, row in enumerate(selected, 1):
        row["number"] = number
    return selected


def readClassifications(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(value not in statuses for value in data.values()):
        raise ValueError(f"Arquivo de classificações inválido: {path}")
    return data


class textureViewer:
    def __init__(self, root, catalog, classificationsPath=statePath):
        self.root = root
        self.catalog = catalog
        self.classificationsPath = classificationsPath
        self.classifications = readClassifications(classificationsPath)
        self.photos = {}
        self.cardButtons = {}
        self.cardFrames = {}
        self.cardLabels = {}
        self.visibleEntries = []
        self.filteredEntries = []
        self.currentEntry = None
        self.previewPhoto = None
        self.ready = False
        self.currentPage = 0
        self.pageSize = pageSize
        self.cacheIndex = 0
        self.cacheQueue = []
        self.cacheAfter = None
        self.failures = []
        self.failedThumbnailIds = set()
        self.rawResourceId = None
        self.rawResource = None
        self.searchAfter = None

        thumbDir.mkdir(parents=True, exist_ok=True)
        self.workDir = cacheDir / "trabalho"
        self.workDir.mkdir(parents=True, exist_ok=True)
        self.createWidgets()
        self.ready = True
        self.root.after(0, self.refreshGrid)

    def createWidgets(self):
        self.root.title("Pokopia — Classificador de texturas")
        self.root.geometry("1450x900")
        self.root.minsize(1100, 700)

        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Buscar ID:").pack(side="left")
        self.searchVar = tk.StringVar()
        self.searchEntry = ttk.Entry(top, textvariable=self.searchVar, width=28)
        self.searchEntry.pack(side="left", padx=(5, 14))
        self.searchVar.trace_add("write", self.scheduleRefresh)
        ttk.Label(top, text="Classificação:").pack(side="left")
        self.filterVar = tk.StringVar(value="Todas")
        self.filterBox = ttk.Combobox(
            top,
            textvariable=self.filterVar,
            values=["Todas", "Sem classificação", "Traduzir", "Ignorar", "Revisar depois"],
            state="readonly",
            width=19,
        )
        self.filterBox.pack(side="left", padx=5)
        self.filterBox.bind("<<ComboboxSelected>>", self.refreshGrid)
        self.progressLabel = ttk.Label(top, text="Carregando catálogo…")
        self.progressLabel.pack(side="right")

        body = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, minsize=760)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        gridPanel = ttk.Frame(body)
        gridPanel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        pageBar = ttk.Frame(gridPanel)
        pageBar.pack(side="bottom", fill="x", pady=(4, 0))
        self.prevPageButton = ttk.Button(pageBar, text="← Página", command=lambda: self.movePage(-1))
        self.prevPageButton.pack(side="left")
        self.pageLabel = ttk.Label(pageBar, text="Página 1/1")
        self.pageLabel.pack(side="left", expand=True)
        self.nextPageButton = ttk.Button(pageBar, text="Próxima →", command=lambda: self.movePage(1))
        self.nextPageButton.pack(side="right")
        self.canvas = tk.Canvas(gridPanel, highlightthickness=0, background="#252525")
        scrollbar = ttk.Scrollbar(gridPanel, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.gridFrame = ttk.Frame(self.canvas)
        self.gridWindow = self.canvas.create_window((0, 0), window=self.gridFrame, anchor="nw")
        self.gridFrame.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.gridWindow, width=event.width))
        self.bindGalleryScroll(self.canvas)
        self.bindGalleryScroll(self.gridFrame)

        detail = ttk.Frame(body, padding=8, relief="groove")
        detail.grid(row=0, column=1, sticky="nsew")
        self.detailTitle = ttk.Label(detail, text="Selecione uma textura", font=("Segoe UI", 12, "bold"))
        self.detailTitle.pack(anchor="w")
        self.detailInfo = ttk.Label(detail, text="")
        self.detailInfo.pack(anchor="w", pady=(4, 10))
        self.previewLabel = ttk.Label(detail, anchor="center")
        self.previewLabel.pack(fill="both", expand=True, pady=5)
        self.selectionStatus = ttk.Label(detail, text="")
        self.selectionStatus.pack(pady=4)

        navigation = ttk.Frame(detail)
        navigation.pack(fill="x", pady=5)
        ttk.Button(navigation, text="← Anterior", command=lambda: self.moveSelection(-1)).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(navigation, text="Próxima →", command=lambda: self.moveSelection(1)).pack(side="left", expand=True, fill="x", padx=2)

        actions = ttk.Frame(detail)
        actions.pack(fill="x", pady=(4, 8))
        for label, status in (("Traduzir", "traduzir"), ("Ignorar", "ignorar"), ("Revisar depois", "revisar_depois")):
            ttk.Button(actions, text=label, command=lambda value=status: self.classify(value)).pack(side="left", expand=True, fill="x", padx=2)
        self.messageLabel = ttk.Label(detail, text="")
        self.messageLabel.pack(anchor="w")

    def thumbPath(self, entry):
        return thumbDir / f"{entry['resourceId'][2:]}_{entry['texIndex']:04d}.png"

    def bindGalleryScroll(self, widget):
        widget.bind("<MouseWheel>", self.scrollGallery)

    def scrollGallery(self, event):
        direction = -1 if event.delta > 0 else 1
        units = max(1, abs(event.delta) // 120)
        self.canvas.yview_scroll(direction * units, "units")
        return "break"

    def validThumbnail(self, path):
        try:
            data = path.read_bytes()[:24]
            width, height = struct.unpack_from(">II", data, 16)
            return data[:8] == b"\x89PNG\r\n\x1a\n" and 0 < width <= 128 and 0 < height <= 128
        except (OSError, struct.error):
            return False

    def prepareNext(self):
        self.cacheAfter = None
        if self.cacheIndex >= len(self.cacheQueue):
            return

        entry = self.cacheQueue[self.cacheIndex]
        path = self.thumbPath(entry)
        try:
            self.createThumbnail(entry, path)
            if entry["id"] in self.cardButtons:
                photo = tk.PhotoImage(file=str(path))
                self.photos[entry["id"]] = photo
                self.cardButtons[entry["id"]].configure(image=photo, text="")
                if self.currentEntry and self.currentEntry["id"] == entry["id"]:
                    self.selectEntry(entry)
        except Exception as error:
            self.failures.append((entry, str(error)))
            self.failedThumbnailIds.add(entry["id"])
            if entry["id"] in self.cardButtons:
                self.cardButtons[entry["id"]].configure(text="Falha na miniatura")
            print(f"{entry['id']}: {error}")

        self.cacheIndex += 1
        if self.cacheIndex < len(self.cacheQueue):
            self.cacheAfter = self.root.after(1, self.prepareNext)

    def readG1t(self, entry):
        path = dumpDir.joinpath(*entry["fdataPath"].split("/"))
        with path.open("rb") as fdata:
            fdata.seek(entry["fdataOffset"])
            if fdata.read(8) != b"IDRK0000":
                raise ValueError("cabeçalho IDRK0000 ausente")
            entrySize, compressedSize, rawSize = struct.unpack("<3Q", fdata.read(24))
            entryType, fileHash, ktid, flags = struct.unpack("<4I", fdata.read(16))
            extraSize = entrySize - compressedSize - 0x30
            if extraSize < 0 or entrySize != entry["storedSize"]:
                raise ValueError("tamanho registrado do FDATA diverge")
            if fileHash != int(entry["resourceId"], 0) or ktid != entry["ktid"]:
                raise ValueError("ID ou KTID do FDATA diverge")
            if entryType != entry["entryType"] or flags != entry["flags"] or rawSize != entry["rawSize"]:
                raise ValueError("metadados do FDATA divergem")

            fdata.seek(extraSize, 1)
            raw = bytearray()
            streamSize = 0
            while len(raw) < rawSize:
                if flags & 0x100000:
                    sizeData = fdata.read(4)
                    if len(sizeData) != 4:
                        raise ValueError("tamanho do bloco FDATA incompleto")
                    blockSize = struct.unpack("<I", sizeData)[0]
                else:
                    sizeData = fdata.read(10)
                    if len(sizeData) != 10:
                        raise ValueError("cabeçalho do bloco FDATA incompleto")
                    blockSize = struct.unpack_from("<H", sizeData)[0]
                blockData = fdata.read(blockSize)
                if not blockSize or len(blockData) != blockSize:
                    raise ValueError("payload zlib FDATA incompleto")
                block = zlib.decompress(blockData)
                if not block or len(raw) + len(block) > rawSize:
                    raise ValueError("bloco zlib FDATA excede o tamanho esperado")
                raw.extend(block)
                streamSize += len(sizeData) + blockSize
            if compressedSize < streamSize or compressedSize - streamSize > 16:
                raise ValueError("tamanho comprimido FDATA inconsistente")
        if raw[:4] != b"GT1G":
            raise ValueError("recurso descomprimido não é G1T")
        return bytes(raw)

    def getG1t(self, entry):
        if self.rawResourceId != entry["resourceId"]:
            self.rawResource = self.readG1t(entry)
            self.rawResourceId = entry["resourceId"]
        return self.rawResource

    def createThumbnail(self, entry, path):
        raw = self.getG1t(entry)
        _, _, _, headerSize, textureCount, platform, _ = struct.unpack_from("<4s6I", raw)
        if platform != 0x18 or entry["texIndex"] >= textureCount:
            raise ValueError("plataforma ou índice de textura inválido")
        tableOffset = headerSize + entry["texIndex"] * 4
        if tableOffset + 4 > len(raw):
            raise ValueError("ponteiro da textura ultrapassa o G1T")
        textureOffset = headerSize + struct.unpack_from("<I", raw, tableOffset)[0]
        if textureOffset + 8 > len(raw) or raw[textureOffset + 1] != int(entry["formatId"], 0):
            raise ValueError("cabeçalho da textura diverge do inventário")
        start = entry["payloadOffset"]
        end = start + entry["payloadSize"]
        if start < textureOffset + 8 or end > len(raw):
            raise ValueError("payload da textura ultrapassa o G1T")

        payloadPath = self.workDir / "payload.bin"
        mipPath = self.workDir / "mip.bin"
        decodedPath = self.workDir / "decoded.png"
        try:
            payloadPath.write_bytes(raw[start:end])
            commonArgs = ["-f", entry["format"], "-w", str(entry["width"]), "-h", str(entry["height"]), "-m", "switch2", "--arg", "auto", "--mips", str(entry["mips"])]
            commands = [
                [str(texcPath), "unswizzle", "-i", str(payloadPath), *commonArgs, "--mip", "0", "-o", str(mipPath)],
                [str(texcPath), "decode", "-i", str(mipPath), "-f", entry["format"], "-w", str(entry["width"]), "-h", str(entry["height"]), "-o", str(decodedPath)],
            ]
            for command in commands:
                result = subprocess.run(command, capture_output=True, text=True, errors="replace")
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"texc encerrou com {result.returncode}")
            image = tk.PhotoImage(file=str(decodedPath))
            largest = max(image.width(), image.height())
            if largest > 128:
                factor = math.ceil(largest / 128)
                image = image.subsample(factor, factor)
            elif largest < 128:
                factor = max(1, 128 // largest)
                image = image.zoom(factor, factor)
            image.write(str(path), format="png")
        finally:
            for tempPath in (payloadPath, mipPath, decodedPath):
                tempPath.unlink(missing_ok=True)

    def scheduleRefresh(self, *_):
        if self.searchAfter:
            self.root.after_cancel(self.searchAfter)
        self.searchAfter = self.root.after(150, self.refreshGrid)

    def refreshGrid(self, *_, preferredId=None):
        if not self.ready:
            return
        selectedId = preferredId or (self.currentEntry["id"] if self.currentEntry else None)
        query = self.searchVar.get().strip().lower()
        selectedFilter = self.filterVar.get()
        filterStatus = {
            "Traduzir": "traduzir",
            "Ignorar": "ignorar",
            "Revisar depois": "revisar_depois",
        }.get(selectedFilter)
        self.filteredEntries = [
            entry for entry in self.catalog
            if (not query or query in entry["id"].lower())
            and (selectedFilter == "Todas" or
                 selectedFilter == "Sem classificação" and entry["id"] not in self.classifications or
                 filterStatus and self.classifications.get(entry["id"]) == filterStatus)
        ]
        selectedIndex = next((index for index, entry in enumerate(self.filteredEntries) if entry["id"] == selectedId), None)
        self.currentPage = selectedIndex // self.pageSize if selectedIndex is not None else 0
        self.renderPage(selectedId)
        self.updateProgress()

    def renderPage(self, selectedId=None):
        if self.cacheAfter:
            self.root.after_cancel(self.cacheAfter)
            self.cacheAfter = None
        self.cacheQueue = []
        self.cacheIndex = 0
        pageCount = max(1, math.ceil(len(self.filteredEntries) / self.pageSize))
        self.currentPage = min(self.currentPage, pageCount - 1)
        start = self.currentPage * self.pageSize
        self.visibleEntries = self.filteredEntries[start:start + self.pageSize]

        for child in self.gridFrame.winfo_children():
            child.destroy()
        self.cardButtons = {}
        self.cardFrames = {}
        self.cardLabels = {}
        self.photos = {}

        colors = {"traduzir": "#d9f0d9", "ignorar": "#e8e8e8", "revisar_depois": "#fff0c2"}
        for index, entry in enumerate(self.visibleEntries):
            card = tk.Frame(self.gridFrame, width=145, height=174, bd=1, relief="solid", bg=colors.get(self.classifications.get(entry["id"]), "#f4f4f4"))
            card.grid(row=index // 5, column=index % 5, padx=3, pady=3)
            card.grid_propagate(False)
            self.bindGalleryScroll(card)
            thumb = self.thumbPath(entry)
            photo = None
            if self.validThumbnail(thumb):
                try:
                    photo = tk.PhotoImage(file=str(thumb))
                except tk.TclError:
                    photo = None
            if photo:
                self.photos[entry["id"]] = photo
                button = tk.Button(card, image=photo, relief="flat", command=lambda item=entry: self.selectEntry(item))
            else:
                text = "Falha na miniatura" if entry["id"] in self.failedThumbnailIds else "Gerando miniatura…"
                button = tk.Button(card, text=text, width=16, height=5, command=lambda item=entry: self.selectEntry(item))
                if entry["id"] not in self.failedThumbnailIds:
                    self.cacheQueue.append(entry)
            button.pack(pady=(4, 1))
            label = tk.Label(card, text=f"{entry['number']:03} · {entry['resourceId']}\nTextura {entry['texIndex']}", bg=card["bg"], font=("Segoe UI", 8))
            label.pack()
            state = self.classifications.get(entry["id"])
            statusLabel = tk.Label(card, text=statusLabels.get(state, "Pendente"), bg=card["bg"], font=("Segoe UI", 8, "bold"))
            statusLabel.pack()
            self.bindGalleryScroll(button)
            self.bindGalleryScroll(label)
            self.bindGalleryScroll(statusLabel)
            label.bind("<Button-1>", lambda event, item=entry: self.selectEntry(item))
            self.cardButtons[entry["id"]] = button
            self.cardFrames[entry["id"]] = card
            self.cardLabels[entry["id"]] = (label, statusLabel)

        self.canvas.yview_moveto(0)
        self.root.after_idle(lambda: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        pageCount = max(1, math.ceil(len(self.filteredEntries) / self.pageSize))
        first = start + 1 if self.visibleEntries else 0
        last = start + len(self.visibleEntries)
        self.pageLabel.configure(text=f"Página {self.currentPage + 1}/{pageCount} · {first}–{last} de {len(self.filteredEntries)}")
        self.prevPageButton.configure(state="normal" if self.currentPage else "disabled")
        self.nextPageButton.configure(state="normal" if self.currentPage + 1 < pageCount else "disabled")
        current = next((entry for entry in self.visibleEntries if entry["id"] == selectedId), None)
        self.selectEntry(current or (self.visibleEntries[0] if self.visibleEntries else None))
        if self.cacheQueue:
            self.cacheAfter = self.root.after(1, self.prepareNext)

    def movePage(self, step):
        pageCount = max(1, math.ceil(len(self.filteredEntries) / self.pageSize))
        nextPage = min(max(0, self.currentPage + step), pageCount - 1)
        if nextPage != self.currentPage:
            self.currentPage = nextPage
            self.renderPage()

    def selectEntry(self, entry):
        oldId = self.currentEntry["id"] if self.currentEntry else None
        if oldId in self.cardButtons:
            self.cardButtons[oldId].configure(relief="flat")
        self.currentEntry = entry
        if not entry:
            self.detailTitle.configure(text="Nenhuma textura encontrada")
            self.detailInfo.configure(text="Ajuste a busca ou o filtro.")
            self.previewLabel.configure(image="")
            self.selectionStatus.configure(text="")
            self.previewPhoto = None
            return
        if entry["id"] in self.cardButtons:
            self.cardButtons[entry["id"]].configure(relief="sunken")
        self.detailTitle.configure(text=f"Textura {entry['number']:03} — {entry['resourceId']}:{entry['texIndex']}")
        self.detailInfo.configure(text=f"Formato {entry['formatId']} ({entry['format']}) · {entry['width']}×{entry['height']} · {entry['mips']} mip")
        thumb = self.photos.get(entry["id"])
        if thumb:
            factor = max(1, 384 // max(thumb.width(), thumb.height()))
            self.previewPhoto = thumb.zoom(factor, factor)
            self.previewLabel.configure(image=self.previewPhoto)
        else:
            self.previewLabel.configure(image="")
            self.previewPhoto = None
        state = self.classifications.get(entry["id"])
        self.selectionStatus.configure(text=statusLabels.get(state, "Sem classificação"))

    def moveSelection(self, step):
        if not self.filteredEntries:
            return
        currentIndex = next((i for i, entry in enumerate(self.filteredEntries) if self.currentEntry and entry["id"] == self.currentEntry["id"]), 0)
        nextIndex = (currentIndex + step) % len(self.filteredEntries)
        entry = self.filteredEntries[nextIndex]
        nextPage = nextIndex // self.pageSize
        if nextPage != self.currentPage:
            self.currentPage = nextPage
            self.renderPage(entry["id"])
        else:
            self.selectEntry(entry)

    def classify(self, status):
        if not self.currentEntry or status not in statuses:
            return
        entry = self.currentEntry
        entryId = entry["id"]
        currentIndex = next((index for index, item in enumerate(self.filteredEntries) if item["id"] == entryId), 0)
        nextEntry = self.filteredEntries[(currentIndex + 1) % len(self.filteredEntries)] if self.filteredEntries else None
        oldStatus = self.classifications.get(entryId)
        self.classifications[entryId] = status
        try:
            self.classificationsPath.parent.mkdir(parents=True, exist_ok=True)
            tempPath = self.classificationsPath.with_suffix(".tmp")
            tempPath.write_text(json.dumps(self.classifications, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tempPath, self.classificationsPath)
        except OSError as error:
            if oldStatus is None:
                self.classifications.pop(entryId, None)
            else:
                self.classifications[entryId] = oldStatus
            self.messageLabel.configure(text=f"Falha ao salvar: {error}")
            return
        self.messageLabel.configure(text="Classificação salva.")

        selectedFilter = self.filterVar.get()
        filterStatus = {
            "Traduzir": "traduzir",
            "Ignorar": "ignorar",
            "Revisar depois": "revisar_depois",
        }.get(selectedFilter)
        removeEntry = selectedFilter == "Sem classificação" or filterStatus and filterStatus != status

        if removeEntry:
            self.refreshGrid(preferredId=nextEntry["id"] if nextEntry else None)
        else:
            color = {"traduzir": "#d9f0d9", "ignorar": "#e8e8e8", "revisar_depois": "#fff0c2"}[status]
            self.cardFrames[entryId].configure(bg=color)
            label, statusLabel = self.cardLabels[entryId]
            label.configure(bg=color)
            statusLabel.configure(text=statusLabels[status], bg=color)

            self.updateProgress()
            self.moveSelection(1)

    def updateProgress(self):
        counts = {status: sum(self.classifications.get(entry["id"]) == status for entry in self.catalog) for status in statuses}
        total = sum(counts.values())
        pending = len(self.catalog) - total
        self.progressLabel.configure(text=f"Classificadas {total}/{len(self.catalog)} · Pendentes {pending} · Traduzir {counts['traduzir']} · Ignorar {counts['ignorar']} · Revisar {counts['revisar_depois']}")


def main():
    global dumpDir
    root = tk.Tk()
    root.withdraw()
    selectedDir = filedialog.askdirectory(title="Selecione a pasta romfs do dump", parent=root)
    if not selectedDir:
        root.destroy()
        return
    dumpDir = Path(selectedDir) / "motor_asset_re" / "KIDS_PLATFORM_OUNCE"
    try:
        if not dumpDir.is_dir() or not texcPath.is_file():
            raise FileNotFoundError("Dump do jogo ou tools\\texc\\texc.exe não encontrado.")
        catalog = loadCatalog()
        root.deiconify()
        textureViewer(root, catalog)
        root.mainloop()
    except Exception as error:
        messagebox.showerror("Pokopia — Classificador de texturas", str(error))
        root.destroy()


if __name__ == "__main__":
    main()
