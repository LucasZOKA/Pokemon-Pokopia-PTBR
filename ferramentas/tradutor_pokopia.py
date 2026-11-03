import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import tkinter as tk
import unicodedata
import zlib
from bisect import bisect_left
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


dumpDir = Path(".")
dataPath = dumpDir / "LD_C0_R.BIN"
indexPath = dumpDir / "LI_C0_R.IDX"
savePath = Path(__file__).resolve().with_name("traducoes.json")
tagPattern = re.compile(r"<([^<>]*)>")
clearPattern = re.compile(rb"<clear>")
languages = (
    "English", "French", "Italian", "German", "Spanish",
    "Traditional Chinese", "Korean", "Simplified Chinese", "Japanese",
)
localeStartRow = 1910
titleId = "0400A3A01EE4C000"
relativeTextRows = {
    2126: "Preferências de habitat",
    2135: "Preferências de habitat",
    2144: "Preferências de habitat",
    2153: "Preferências de habitat",
    2162: "Preferências de habitat",
    2171: "Personalização",
    2216: "Objetivos, tutoriais e opções",
    2225: "Objetivos, tutoriais e opções",
    2252: "Personalização",
    2306: "Preferências de habitat",
    4538: "Nomes de habitat",
    4547: "Descrições de habitat",
    4628: "Rótulos de habitat",
    4871: "Rótulos de estilo",
    5006: "Rótulos de construção",
    2234: "Objetivos, tutoriais e opções",
    2270: "Objetivos, tutoriais e opções",
    2279: "Interface e sistema",
    2324: "Objetivos, tutoriais e opções",
    2333: "Interface e sistema",
    2378: "Interface e sistema",
    4142: "Interface e sistema",
    4196: "Falas curtas dos Pokémon",
    4529: "Interface e sistema",
    4556: "Personalização",
    4601: "Interface e sistema",
    4610: "Interface e sistema",
    4619: "Interface e sistema",
    4655: "Interface e sistema",
    4565: "Personalização",
    4673: "Personalização",
    4682: "Interface e sistema",
    4817: "Interface e sistema",
    4826: "Interface e sistema",
    4835: "Notificações",
    4844: "Interface e sistema",
    4853: "Interface e sistema",
    4862: "Interface e sistema",
    4880: "Interface e sistema",
    4889: "Descrições da Pokédex",
    4916: "Classificações da Pokédex",
    4961: "Interface e sistema",
    4970: "Notificações",
    4997: "Interface e sistema",
    5015: "Notificações",
    5024: "Notificações",
    5033: "Falas curtas dos Pokémon",
    5051: "Personalização",
    5060: "Objetivos, tutoriais e opções",
    5078: "Interface e sistema",
    5087: "Nomes de regiões",
    5114: "Objetivos, tutoriais e opções",
    5141: "Interface e sistema",
    5150: "Objetivos, tutoriais e opções",
    5159: "Objetivos, tutoriais e opções",
    5186: "Objetivos, tutoriais e opções",
    5123: "Interface e sistema",
    5132: "Interface e sistema",
    5177: "Objetivos, tutoriais e opções",
    5195: "Objetivos, tutoriais e opções",
    5204: "Objetivos, tutoriais e opções",
    5213: "Personalização",
    4187: "Falas curtas dos Pokémon",
    4700: "Textos de leitura",
    4709: "Textos de leitura",
    4718: "Textos de leitura",
    4727: "Textos de leitura",
    4736: "Textos de leitura",
    4745: "Textos de leitura",
    4754: "Descrições de itens",
    4763: "Textos de leitura",
    4772: "Textos de leitura",
    4781: "Textos de leitura",
    4790: "Textos de leitura",
    4799: "Descrições de itens",
}
categories = (
    "Diálogos", "Nomes de itens", "Descrições de itens",
    "Nomes de habitat", "Descrições de habitat", "Rótulos de habitat",
    "Rótulos de construção", "Rótulos de estilo",
    "Interface e sistema", "Objetivos, tutoriais e opções",
    "Falas curtas dos Pokémon", "Preferências de habitat",
    "Descrições da Pokédex", "Classificações da Pokédex",
    "Notificações", "Personalização", "Textos de leitura",
    "Nomes de regiões",
)


def getRecordSize(row):
    englishRow = localeStartRow + (row - localeStartRow) // len(languages) * len(languages)
    return {4646: 32, 4538: 12}.get(englishRow, 8)


def getTextFields(raw, recordSize, resourceBase=None):
    if len(raw) < 0x40 or recordSize not in (8, 12, 32):
        raise ValueError("Formato de tabela de textos inválido.")
    count, kind = struct.unpack_from("<II", raw)
    tableEnd = 0x40 + count * recordSize
    isScriptTextTable = kind == 0 and recordSize == 8 and resourceBase == 0x008B5C00
    if (kind != 2 and not isScriptTextTable) or not count or tableEnd + 1 > len(raw):
        raise ValueError("Cabeçalho de tabela de textos inválido.")
    if 0x40 + struct.unpack_from("<I", raw, 0x40)[0] != tableEnd:
        raise ValueError("Formato do registro não corresponde ao recurso.")
    pointerBytes = {8: 4, 12: 8, 32: 24}[recordSize]
    fields = []
    for cell in range(0x40, tableEnd, recordSize):
        for field in range(cell, cell + pointerBytes, 4):
            target = field + struct.unpack_from("<I", raw, field)[0]
            end = raw.find(b"\0", target)
            if not tableEnd <= target <= end < len(raw):
                raise ValueError("Destino de texto inválido.")
            raw[target:end].decode("utf-8")
            fields.append((field, target, end))
    return tableEnd, fields


def sameCommands(original, translated):
    originalTags = tagPattern.findall(original)
    translatedTags = tagPattern.findall(translated)
    if (len(originalTags) != len(translatedTags)
            or original.count("<") != len(originalTags)
            or original.count(">") != len(originalTags)
            or translated.count("<") != len(translatedTags)
            or translated.count(">") != len(translatedTags)):
        return False

    qtyPattern = re.compile(r"qty;([^(),<>]+)\(([^(),<>]+),([^(),<>]+)\)")
    for originalTag, translatedTag in zip(originalTags, translatedTags):
        if originalTag == translatedTag:
            continue
        originalQty = qtyPattern.fullmatch(originalTag)
        translatedQty = qtyPattern.fullmatch(translatedTag)
        if (not originalQty or not translatedQty
                or originalQty.group(1) != translatedQty.group(1)):
            return False
    return True


def validateTextResource(original, rebuilt, recordSize, expectedFields, positions, resourceBase=None):
    tableEnd, fields = getTextFields(rebuilt, recordSize, resourceBase)
    originalTable = bytearray(original[:tableEnd])
    rebuiltTable = bytearray(rebuilt[:tableEnd])
    targets = {}
    for field, target, end in fields:
        if rebuilt[target:end] != expectedFields[field]:
            raise ValueError(f"Texto incorreto no campo {field:08X}.")
        targets[field] = target
        originalTable[field:field + 4] = rebuiltTable[field:field + 4] = b"\0" * 4
    if originalTable != rebuiltTable:
        raise ValueError("Cabeçalho ou metadados de texto foram alterados.")
    for entryId, (field, offset, text) in positions.items():
        target = targets[field] + offset
        if rebuilt[target:target + len(text)] != text:
            raise ValueError(f"Tradução incorreta para o ID {entryId}.")


def rebuildTextResource(raw, savedEntries, recordSize, resourceBase=None):
    tableEnd, fields = getTextFields(raw, recordSize, resourceBase)
    cursor = tableEnd
    for start, end in sorted({(start, end) for _, start, end in fields}):
        if start != cursor:
            raise ValueError("Bloco de textos contém dados sem referência ou strings sobrepostas.")
        cursor = end + 1
    if raw[cursor:] != b"\0" * (-cursor & 7):
        raise ValueError("Alinhamento ou dados finais do recurso desconhecidos.")

    savedEntries = sorted(savedEntries)
    offsets = [offset for offset, _, _ in savedEntries]
    rebuilt = bytearray(raw[:tableEnd])
    expectedFields = {}
    positions = {}
    for field, start, end in fields:
        target = len(rebuilt)
        value = bytearray()
        cursor = start
        first = bisect_left(offsets, start)
        last = bisect_left(offsets, end)
        for offset, entryId, text in savedEntries[first:last]:
            if offset < cursor or (offset != start and raw[offset - 7:offset] != b"<clear>"):
                raise ValueError(f"ID sobreposto ou fora do início de um texto: {entryId}")
            clear = raw.find(b"<clear>", offset, end)
            stop = clear + 7 if clear >= 0 else end
            oldText = raw[offset:stop].decode("utf-8")
            newText = text.decode("utf-8")
            if not sameCommands(oldText, newText):
                raise ValueError(f"Comandos internos diferentes em {entryId}.")
            value.extend(raw[cursor:offset])
            positions[entryId] = (field, len(value), text)
            value.extend(text)
            cursor = stop
        value.extend(raw[cursor:end])
        expectedFields[field] = bytes(value)
        struct.pack_into("<I", rebuilt, field, target - field)
        rebuilt.extend(value)
        rebuilt.append(0)
    rebuilt.extend(b"\0" * (-len(rebuilt) & 7))
    if len(positions) != len(savedEntries):
        raise ValueError("Há traduções sem referência na tabela original.")
    rebuilt = bytes(rebuilt)
    validateTextResource(raw, rebuilt, recordSize, expectedFields, positions, resourceBase)
    return rebuilt, expectedFields, positions


def displayText(rawText):
    def showTag(match):
        tag = match.group(1)
        name = tag.lower()
        if name in ("br", "clear", "slide"):
            return "\n"
        if name.startswith(("pname;", "acqpname;", "nowner;", "fqty(", "usingp;")) or name == "class":
            return f"[{tag}]"
        return ""

    return tagPattern.sub(showTag, rawText).strip()


def isReadable(rawText, language):
    tags = tagPattern.findall(rawText)
    if rawText.count("<") != len(tags) or rawText.count(">") != len(tags):
        return False
    text = re.sub(r"\[[^\]]*\]", " ", displayText(rawText)).replace("\n", " ").strip()
    if not text or "\ufffd" in text or not all(char.isprintable() or char.isspace() for char in text):
        return False
    if any(char in "_$@#|\\/" for char in text):
        return False
    letters = sum(char.isalpha() for char in text)
    if letters / len(text) < 0.5:
        return False
    if language in languages[5:] and any(ord(char) > 127 and char.isalpha() for char in text):
        return True
    words = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", text)
    return len(words) >= 2 or bool(re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ]+[!?.,…'’\-]+", text))


def normalizeSearchText(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(char for char in text if not unicodedata.combining(char)).split())


def filterEntries(entries, query, language, category):
    query = normalizeSearchText(query)
    return [
        entry for entry in entries
        if entry["category"] == category and entry["language"] == language and (
            not query or query in normalizeSearchText(entry["original"])
            or query in normalizeSearchText(displayText(entry["translation"]))
        )
    ]


def loadDialogs():
    index = indexPath.read_bytes()
    if len(index) % 32:
        raise ValueError("O índice LI_C0_R.IDX está incompleto.")

    entries = []
    seenStreams = set()
    dataSize = dataPath.stat().st_size
    with dataPath.open("rb") as dataFile:
        for row, indexOffset in enumerate(range(0, len(index), 32)):
            if row < localeStartRow:
                continue
            resourceBase = struct.unpack_from("<Q", index, indexOffset)[0]
            streamOffset = resourceBase + 0x84
            if streamOffset in seenStreams or streamOffset < 0x84 or streamOffset > dataSize:
                continue
            seenStreams.add(streamOffset)
            language = languages[(row - localeStartRow) % len(languages)]

            try:
                _, rawBlock, _ = readResource(dataFile, resourceBase)
            except (OSError, ValueError, zlib.error):
                continue
            if b"<$" not in rawBlock and b"<clear>" not in rawBlock:
                continue

            for fieldMatch in re.finditer(rb"[^\x00]+", rawBlock):
                field = fieldMatch.group()
                if b"<" not in field:
                    continue
                try:
                    field.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                partStart = 0
                for clearMatch in clearPattern.finditer(field):
                    partEnd = clearMatch.end()
                    rawText = field[partStart:partEnd].decode("utf-8")
                    if isReadable(rawText, language):
                        rawOffset = fieldMatch.start() + partStart
                        entries.append({
                            "id": f"{streamOffset:08X}:{rawOffset:08X}",
                            "raw": rawText,
                            "original": displayText(rawText),
                            "commands": tagPattern.findall(rawText),
                            "language": language,
                            "category": "Diálogos",
                            "translation": "",
                            "reviewed": False,
                        })
                    partStart = partEnd

                rawText = field[partStart:].decode("utf-8")
                if isReadable(rawText, language):
                    rawOffset = fieldMatch.start() + partStart
                    entries.append({
                        "id": f"{streamOffset:08X}:{rawOffset:08X}",
                        "raw": rawText,
                        "original": displayText(rawText),
                        "commands": tagPattern.findall(rawText),
                        "language": language,
                        "category": "Diálogos",
                        "translation": "",
                        "reviewed": False,
                    })

    if not entries:
        raise ValueError("Nenhum diálogo legível foi encontrado no dump.")
    return entries


def readResource(dataFile, base):
    dataFile.seek(base)
    header = dataFile.read(0x80)
    if len(header) != 0x80:
        raise ValueError("Cabeçalho de recurso incompleto.")

    chunkSize, chunkCount, totalSize = struct.unpack_from("<III", header)
    if not chunkSize or not chunkCount or chunkCount > 29 or totalSize > chunkSize * chunkCount:
        raise ValueError("Cabeçalho de recurso inválido.")

    chunks = []
    position = base + 0x80
    for number in range(chunkCount):
        storedSize = struct.unpack_from("<I", header, 12 + number * 4)[0]
        dataFile.seek(position)
        sizeBytes = dataFile.read(4)
        if len(sizeBytes) != 4:
            raise ValueError("Tamanho de bloco incompleto.")
        compressedSize = struct.unpack("<I", sizeBytes)[0]
        compressed = dataFile.read(compressedSize)
        if storedSize != compressedSize + 4 or len(compressed) != compressedSize:
            raise ValueError("Tamanho de bloco inconsistente.")
        rawChunk = zlib.decompress(compressed)
        expectedSize = min(chunkSize, totalSize - number * chunkSize)
        if len(rawChunk) != expectedSize:
            raise ValueError("Tamanho descomprimido inconsistente.")
        chunks.append(rawChunk)
        position = (position + compressedSize + 4 + 0x7F) & ~0x7F

    return header, b"".join(chunks), position - base


def loadItemEntries():
    index = indexPath.read_bytes()
    if len(index) % 32:
        raise ValueError("O índice LI_C0_R.IDX está incompleto.")

    entries = []
    with dataPath.open("rb") as dataFile:
        for row, category in ((4646, "Nomes de itens"), (4637, "Descrições de itens")):
            language = languages[(row - localeStartRow) % len(languages)]
            if language != "English":
                raise ValueError(f"O recurso da categoria {category} não está em inglês.")
            base = struct.unpack_from("<Q", index, row * 32)[0]
            _, raw, _ = readResource(dataFile, base)
            _, fields = getTextFields(raw, getRecordSize(row))
            for _, offset, end in fields:
                try:
                    rawText = raw[offset:end].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if (not rawText.strip()
                        or not all(char.isprintable() or char.isspace() for char in rawText)
                        or sum(char.isalpha() for char in rawText) < 2):
                    continue
                commands = tagPattern.findall(rawText)
                if rawText.count("<") != len(commands) or rawText.count(">") != len(commands):
                    continue

                entries.append({
                    "id": f"{base + 0x84:08X}:{offset:08X}",
                    "raw": rawText,
                    "original": rawText,
                    "commands": commands,
                    "language": language,
                    "category": category,
                    "translation": "",
                    "reviewed": False,
                })
    return entries


def loadRelativeTextEntries(existingIds):
    index = indexPath.read_bytes()
    if len(index) % 32:
        raise ValueError("O índice LI_C0_R.IDX está incompleto.")

    expectedCounts = {
        2126: 2, 2135: 2, 2144: 2, 2153: 51, 2162: 35, 2171: 21,
        2216: 1, 2225: 1, 2252: 27, 2306: 21,
        4538: 514, 4547: 257, 4628: 74, 4871: 30, 5006: 11,
        2234: 256, 2270: 1601, 2279: 8, 2324: 173, 2333: 47,
        2378: 5, 4142: 8, 4529: 58, 4601: 9, 4610: 517,
        4196: 89, 4556: 20, 4565: 32, 4619: 15, 4655: 232,
        4673: 41, 4682: 10, 4817: 15, 4826: 4, 4835: 51,
        4844: 8, 4853: 7, 4862: 2, 4880: 6, 4889: 374, 4916: 374,
        4961: 18, 4970: 2, 4997: 5, 5015: 6, 5024: 6, 5033: 10,
        5051: 33, 5060: 50, 5078: 33,
        5114: 10, 5123: 223, 5132: 21, 5177: 202, 5195: 72,
        5141: 4, 5150: 2, 5159: 9, 5186: 4, 5204: 33, 5213: 41,
        4187: 90, 4700: 34, 4709: 6, 4718: 56, 4727: 18,
        4736: 15, 4745: 4, 4754: 13, 4763: 29, 4772: 8,
        4781: 8, 4790: 5, 4799: 5, 5087: 9,
    }
    existingIds = set(existingIds)
    entries = []
    with dataPath.open("rb") as dataFile:
        for row, category in relativeTextRows.items():
            if languages[(row - localeStartRow) % len(languages)] != "English":
                raise ValueError(f"O recurso da categoria {category} não está em inglês.")
            base = struct.unpack_from("<Q", index, row * 32)[0]
            _, raw, _ = readResource(dataFile, base)
            _, fields = getTextFields(raw, getRecordSize(row))
            rowEntries = []
            for _, textOffset, textEnd in fields:
                try:
                    rawText = raw[textOffset:textEnd].decode("utf-8")
                except UnicodeDecodeError:
                    continue
                commands = tagPattern.findall(rawText)
                if (not rawText.strip()
                        or not all(char.isprintable() or char.isspace() for char in rawText)
                        or sum(char.isalpha() for char in rawText) < 2
                        or rawText.count("<") != len(commands)
                        or rawText.count(">") != len(commands)):
                    continue

                entryId = f"{base + 0x84:08X}:{textOffset:08X}"
                if (category in ("Interface e sistema", "Objetivos, tutoriais e opções")
                        and entryId in existingIds):
                    continue
                rowEntries.append({
                    "id": entryId,
                    "raw": rawText,
                    "original": displayText(rawText),
                    "commands": commands,
                    "language": "English",
                    "category": category,
                    "translation": "",
                    "reviewed": False,
                })
                existingIds.add(entryId)

            if len(rowEntries) != expectedCounts[row]:
                raise ValueError(
                    f"Quantidade inesperada de textos em {category}: {len(rowEntries)}."
                )
            entries.extend(rowEntries)
    return entries


def makeResourceRecord(header, raw):
    chunkSize, oldChunkCount = struct.unpack_from("<II", header)
    chunks = [raw[offset:offset + chunkSize] for offset in range(0, len(raw), chunkSize)]
    if not chunks or len(chunks) > 29:
        raise ValueError("Quantidade de blocos de recurso inválida.")

    resultHeader = bytearray(header)
    struct.pack_into("<III", resultHeader, 0, chunkSize, len(chunks), len(raw))
    for number in range(max(oldChunkCount, len(chunks))):
        struct.pack_into("<I", resultHeader, 12 + number * 4, 0)

    record = bytearray(resultHeader)
    for number, rawChunk in enumerate(chunks):
        compressed = zlib.compress(rawChunk, 9)
        struct.pack_into("<I", resultHeader, 12 + number * 4, len(compressed) + 4)
        record.extend(struct.pack("<I", len(compressed)))
        record.extend(compressed)
        record.extend(b"\0" * (-len(record) & 0x7F))

    record[:0x80] = resultHeader
    return bytes(record)


def buildModFiles(outputDir):
    savedData = json.loads(savePath.read_text(encoding="utf-8"))
    if not isinstance(savedData, dict):
        raise ValueError("O arquivo traducoes.json não contém um objeto JSON válido.")
    translations = savedData.get("translations", {})
    if not isinstance(translations, dict):
        raise ValueError("O formato de traducoes.json é inválido.")

    index = bytearray(indexPath.read_bytes())
    if len(index) % 32:
        raise ValueError("O índice LI_C0_R.IDX está incompleto.")

    streamRows = {}
    usedBases = set()
    for indexOffset in range(0, len(index), 32):
        base = struct.unpack_from("<Q", index, indexOffset)[0]
        usedBases.add(base)
        streamRows.setdefault(base + 0x84, []).append(indexOffset)

    groupedTranslations = {}
    for entryId, translation in translations.items():
        if not translation:
            continue
        if not isinstance(translation, str) or "\0" in translation:
            raise ValueError(f"Tradução inválida: {entryId}")
        try:
            streamText, offsetText = entryId.split(":")
            stream, offset = int(streamText, 16), int(offsetText, 16)
        except (ValueError, TypeError):
            raise ValueError(f"ID de texto inválido: {entryId}") from None
        groupedTranslations.setdefault(stream, []).append((offset, entryId, translation.encode("utf-8")))

    if not groupedTranslations:
        raise ValueError("Não há traduções salvas para gerar o mod.")

    resources = {}
    appliedCount = 0
    with dataPath.open("rb") as sourceFile:
        for stream, savedEntries in groupedTranslations.items():
            rowOffsets = streamRows.get(stream)
            if not rowOffsets:
                raise ValueError(f"Recurso ausente para {stream:08X}.")
            sizes = {getRecordSize(row // 32) for row in rowOffsets}
            if len(sizes) != 1:
                raise ValueError("Formatos conflitantes para o mesmo recurso.")
            textRecordSize = sizes.pop()
            resourceBase = stream - 0x84
            header, original, recordSize = readResource(sourceFile, resourceBase)
            for row in rowOffsets:
                if (struct.unpack_from("<I", index, row + 8)[0] != len(original)
                        or struct.unpack_from("<I", index, row + 16)[0] != recordSize):
                    raise ValueError(f"Indice original inconsistente para {stream:08X}.")
            rebuilt, expectedFields, positions = rebuildTextResource(
                original, savedEntries, textRecordSize, resourceBase,
            )
            record = makeResourceRecord(header, rebuilt)
            resources[stream] = (
                rowOffsets, original, rebuilt, record, textRecordSize, expectedFields, positions,
            )
            appliedCount += len(positions)

    outputDir.mkdir(parents=True, exist_ok=True)
    outputDataPath = outputDir / "LD_C0_R.BIN"
    outputIndexPath = outputDir / "LI_C0_R.IDX"
    if outputDataPath.resolve() == dataPath.resolve():
        raise ValueError("A saída não pode substituir o dump original.")
    shutil.copyfile(dataPath, outputDataPath)

    newBases = {}
    with outputDataPath.open("ab") as outputFile:
        for stream, resource in resources.items():
            rowOffsets, _, raw, record, _, _, _ = resource
            padding = -outputFile.tell() & 0xFF
            if padding:
                outputFile.write(b"\0" * padding)
            while outputFile.tell() in usedBases:
                outputFile.write(b"\0" * 0x100)
            newBase = outputFile.tell()
            usedBases.add(newBase)
            outputFile.write(record)
            newBases[stream] = newBase
            for rowOffset in rowOffsets:
                struct.pack_into("<Q", index, rowOffset, newBase)
                struct.pack_into("<I", index, rowOffset + 8, len(raw))
                struct.pack_into("<I", index, rowOffset + 16, len(record))

    outputIndexPath.write_bytes(index)
    verifiedIndex = outputIndexPath.read_bytes()
    if verifiedIndex != index:
        raise ValueError("Validação IDX falhou após a gravação.")
    with outputDataPath.open("rb") as outputFile:
        for stream, resource in resources.items():
            rowOffsets, original, expected, record, textRecordSize, expectedFields, positions = resource
            base = newBases[stream]
            recordSize = len(record)
            _, actual, actualRecordSize = readResource(outputFile, base)
            if actual != expected or actualRecordSize != recordSize:
                raise ValueError(f"Validação BIN falhou para {stream:08X}.")
            validateTextResource(original, actual, textRecordSize, expectedFields, positions, stream - 0x84)
            for rowOffset in streamRows[stream]:
                if struct.unpack_from("<Q", verifiedIndex, rowOffset)[0] != base:
                    raise ValueError(f"Validação IDX falhou para {stream:08X}.")
                if struct.unpack_from("<I", verifiedIndex, rowOffset + 8)[0] != len(actual):
                    raise ValueError(f"Tamanho IDX inválido para {stream:08X}.")
                if struct.unpack_from("<I", verifiedIndex, rowOffset + 16)[0] != recordSize:
                    raise ValueError(f"Registro IDX inválido para {stream:08X}.")

    return appliedCount, newBases


def generateMod():
    appData = os.environ.get("APPDATA")
    if not appData:
        raise OSError("A pasta APPDATA não foi encontrada.")
    modDir = Path(appData) / "eden" / "load" / titleId / "TraducaoBR"
    romfsDir = modDir / "romfs"
    if not romfsDir.is_dir():
        raise FileNotFoundError(f"Mod TraducaoBR não encontrado: {romfsDir}")
    for name in ("LD_C0_R.BIN", "LI_C0_R.IDX"):
        if not (romfsDir / name).is_file():
            raise FileNotFoundError(f"Arquivo do mod não encontrado: {romfsDir / name}")
    backupDir = modDir.parent / ".TraducaoBR-romfs-backup"
    if backupDir.exists():
        raise FileExistsError(f"Remova ou restaure o backup existente: {backupDir}")

    with tempfile.TemporaryDirectory(prefix="TraducaoBR-", dir=modDir.parent) as tempName:
        stageDir = Path(tempName) / "romfs"
        stageDir.mkdir()
        for source in romfsDir.iterdir():
            if source.name in ("LD_C0_R.BIN", "LI_C0_R.IDX"):
                continue
            target = stageDir / source.name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)

        appliedCount, _ = buildModFiles(stageDir)
        expectedHashes = {}
        for name in ("LD_C0_R.BIN", "LI_C0_R.IDX"):
            with (stageDir / name).open("rb") as dataFile:
                expectedHashes[name] = hashlib.file_digest(dataFile, "sha256").digest()
        os.replace(romfsDir, backupDir)
        try:
            os.replace(stageDir, romfsDir)
            for name, expectedHash in expectedHashes.items():
                with (romfsDir / name).open("rb") as dataFile:
                    if hashlib.file_digest(dataFile, "sha256").digest() != expectedHash:
                        raise ValueError(f"Arquivo instalado difere do arquivo validado: {name}")
        except Exception as installError:
            try:
                if romfsDir.exists():
                    os.replace(romfsDir, Path(tempName) / "romfs-failed")
                os.replace(backupDir, romfsDir)
            except OSError as restoreError:
                raise OSError(
                    f"Falha ao restaurar o mod anterior; backup preservado em {backupDir}: {restoreError}"
                ) from installError
            raise
        try:
            shutil.rmtree(backupDir)
        except OSError:
            pass

    return appliedCount


def main():
    global dumpDir, dataPath, indexPath
    root = tk.Tk()
    root.withdraw()
    selectedDir = filedialog.askdirectory(title="Selecione a pasta romfs do dump", parent=root)
    if not selectedDir:
        root.destroy()
        return
    dumpDir = Path(selectedDir)
    dataPath, indexPath = dumpDir / "LD_C0_R.BIN", dumpDir / "LI_C0_R.IDX"
    root.deiconify()
    root.title("Pokopia Translator - Tradução PT-BR")
    root.geometry("1180x760")
    root.minsize(900, 600)
    root.configure(bg="#20242b")

    loadingLabel = tk.Label(root, text="Lendo textos do dump...", bg="#20242b", fg="#f1f3f5", font=("Segoe UI", 12))
    loadingLabel.pack(expand=True)
    root.update_idletasks()
    try:
        entries = loadDialogs()
        entries.extend(loadItemEntries())
        relativeEntries = loadRelativeTextEntries(entry["id"] for entry in entries)
        relativeIds = {entry["id"] for entry in relativeEntries}
        entries = [
            entry for entry in entries
            if entry["category"] != "Diálogos" or entry["id"] not in relativeIds
        ]
        entries.extend(relativeEntries)
        if len({entry["id"] for entry in entries}) != len(entries):
            raise ValueError("A extração gerou IDs duplicados.")
        savedData = json.loads(savePath.read_text(encoding="utf-8")) if savePath.exists() else {}
    except (OSError, ValueError, json.JSONDecodeError) as error:
        messagebox.showerror("Pokopia Translator", str(error), parent=root)
        root.destroy()
        return
    if not isinstance(savedData, dict):
        messagebox.showerror("Pokopia Translator", "O arquivo traducoes.json não contém um objeto JSON válido.", parent=root)
        root.destroy()
        return

    translations = savedData.get("translations", {})
    reviewedIds = set(savedData.get("reviewed", []))
    if not isinstance(translations, dict) or not isinstance(savedData.get("reviewed", []), list):
        messagebox.showerror("Pokopia Translator", "O formato de traducoes.json é inválido.", parent=root)
        root.destroy()
        return
    for entry in entries:
        entry["translation"] = translations.get(entry["id"], "")
        entry["reviewed"] = entry["id"] in reviewedIds

    loadingLabel.destroy()
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background="#20242b")
    style.configure("TLabel", background="#20242b", foreground="#f1f3f5")
    style.configure("TButton", background="#353b44", foreground="#f1f3f5", padding=(10, 6), borderwidth=0)
    style.map("TButton", background=[("active", "#454d58")])
    style.configure("TCheckbutton", background="#20242b", foreground="#f1f3f5")
    style.configure("Horizontal.TProgressbar", troughcolor="#343a43", background="#33c59b")

    searchVar = tk.StringVar()
    categoryVar = tk.StringVar(value="Diálogos")
    languageVar = tk.StringVar(value="English")
    reviewVar = tk.BooleanVar()
    statusVar = tk.StringVar(value=f"{len(entries):,} textos carregados")
    visibleEntries = []
    currentEntry = None
    currentPosition = -1
    pinnedEntryId = None
    saveAfter = None
    filterAfter = None
    loadingEntry = False
    dirtyTranslationIds = set()
    dirtyReviewIds = set()

    header = ttk.Frame(root, padding=(14, 12))
    header.pack(fill="x")
    ttk.Label(header, text="Pokopia · Tradução PT-BR", font=("Segoe UI", 16, "bold")).pack(side="left")
    categorySelect = ttk.Combobox(
        header, textvariable=categoryVar,
        values=categories,
        state="readonly", width=31,
    )
    categorySelect.pack(side="left", padx=(18, 8))
    searchEntry = ttk.Entry(header, textvariable=searchVar, width=22)
    searchEntry.pack(side="left", padx=(4, 8))
    ttk.Label(header, text="Buscar").pack(side="left")
    progressLabel = ttk.Label(header, text="")
    progressLabel.pack(side="right")
    ttk.Label(header, text="Idioma").pack(side="right", padx=(12, 6))
    languageSelect = ttk.Combobox(
        header, textvariable=languageVar, values=languages, state="readonly", width=18,
    )
    languageSelect.pack(side="right")

    progress = ttk.Progressbar(root, mode="determinate", style="Horizontal.TProgressbar")
    progress.pack(fill="x", padx=14)

    content = ttk.Panedwindow(root, orient="horizontal")
    content.pack(fill="both", expand=True, padx=14, pady=12)
    listFrame = ttk.Frame(content, padding=(0, 0, 8, 0))
    editorFrame = ttk.Frame(content, padding=(8, 0, 0, 0))
    content.add(listFrame, weight=1)
    content.add(editorFrame, weight=2)

    dialogList = tk.Listbox(
        listFrame, bg="#15191f", fg="#e8ebef", selectbackground="#1767c8",
        selectforeground="white", activestyle="none", relief="flat", borderwidth=0,
        exportselection=False, font=("Segoe UI", 10),
    )
    listScroll = ttk.Scrollbar(listFrame, orient="vertical", command=dialogList.yview)
    dialogList.configure(yscrollcommand=listScroll.set)
    listScroll.pack(side="right", fill="y")
    dialogList.pack(side="left", fill="both", expand=True)

    positionLabel = ttk.Label(editorFrame, text="", font=("Segoe UI", 11, "bold"))
    positionLabel.pack(anchor="w", pady=(0, 8))
    originalLabel = ttk.Label(editorFrame, text="Texto original (English)", font=("Segoe UI", 10, "bold"))
    originalLabel.pack(anchor="w")
    originalText = tk.Text(
        editorFrame, height=8, wrap="word", bg="#e5e7eb", fg="#15191f",
        relief="flat", padx=10, pady=9, font=("Segoe UI", 11),
    )
    originalText.pack(fill="x", pady=(5, 14))
    originalText.configure(state="disabled")

    ttk.Label(editorFrame, text="Tradução (PT-BR)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    ttk.Label(editorFrame, text="As marcações azuis entre <...> devem permanecer iguais às originais.").pack(anchor="w", pady=(2, 4))
    translationText = tk.Text(
        editorFrame, height=12, wrap="word", bg="#f4f5f7", fg="#15191f",
        insertbackground="#15191f", selectbackground="#2775d5", relief="flat",
        padx=10, pady=9, font=("Segoe UI", 11), undo=True, autoseparators=True,
    )
    translationText.pack(fill="both", expand=True)
    translationText.tag_configure("command", foreground="#1767c8", font=("Consolas", 10, "bold"))

    controls = ttk.Frame(editorFrame, padding=(0, 10, 0, 0))
    controls.pack(fill="x")
    previousButton = ttk.Button(controls, text="← Anterior")
    previousButton.pack(side="left")
    nextButton = ttk.Button(controls, text="Próximo →")
    nextButton.pack(side="left", padx=8)
    reviewCheck = ttk.Checkbutton(controls, text="Marcar como revisado", variable=reviewVar)
    reviewCheck.pack(side="left", padx=(16, 0))

    footer = ttk.Frame(root, padding=(14, 4, 14, 10))
    footer.pack(fill="x")
    ttk.Label(footer, textvariable=statusVar).pack(side="left")
    footerActions = ttk.Frame(footer)
    footerActions.pack(side="right")
    ttk.Label(footer, text=f"JSON: {savePath.name}").pack(side="right", padx=(12, 0))

    def isTranslated(entry):
        return bool(entry["translation"]) and (
            displayText(entry["translation"]).strip() != displayText(entry["raw"]).strip()
        )

    def updateEntryColor(position, entry):
        color = "#55d68b" if entry["reviewed"] else "#68a9ff" if isTranslated(entry) else "#e8ebef"
        dialogList.itemconfigure(position, foreground=color)

    def updateProgress():
        categoryEntries = [
            entry for entry in entries
            if entry["category"] == categoryVar.get() and entry["language"] == languageVar.get()
        ]
        translatedCount = sum(isTranslated(entry) for entry in categoryEntries)
        reviewedCount = sum(entry["reviewed"] for entry in categoryEntries)
        progress["maximum"] = max(1, len(categoryEntries))
        progress["value"] = translatedCount
        progressLabel.configure(text=f"Traduzidos {translatedCount:,} · Revisados {reviewedCount:,} · Pendentes {len(categoryEntries) - translatedCount:,}")

    def saveData():
        nonlocal saveAfter
        saveAfter = None
        try:
            latestData = json.loads(savePath.read_text(encoding="utf-8")) if savePath.exists() else {}
            if not isinstance(latestData, dict):
                raise ValueError("O formato de traducoes.json é inválido.")
            latestTranslations = latestData.get("translations", {})
            latestReviewed = latestData.get("reviewed", [])
            if not isinstance(latestTranslations, dict) or not isinstance(latestReviewed, list):
                raise ValueError("O formato de traducoes.json é inválido.")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            statusVar.set(f"Falha ao ler JSON: {error}")
            return False

        latestTranslations = dict(latestTranslations)
        latestReviewed = set(latestReviewed)
        for entry in entries:
            if entry["id"] in dirtyTranslationIds:
                if entry["translation"]:
                    latestTranslations[entry["id"]] = entry["translation"]
                else:
                    latestTranslations.pop(entry["id"], None)
            if entry["id"] in dirtyReviewIds:
                if entry["reviewed"]:
                    latestReviewed.add(entry["id"])
                else:
                    latestReviewed.discard(entry["id"])

        payload = dict(latestData)
        payload.update({
            "source": latestData.get("source", str(dataPath)),
            "translations": latestTranslations,
            "reviewed": sorted(latestReviewed),
        })
        tempPath = savePath.with_suffix(".tmp")
        try:
            tempPath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tempPath, savePath)
            dirtyTranslationIds.clear()
            dirtyReviewIds.clear()
            statusVar.set(f"Salvo automaticamente · {len(payload['translations']):,} traduções")
            return True
        except OSError as error:
            statusVar.set(f"Falha ao salvar JSON: {error}")
            return False

    def scheduleSave():
        nonlocal saveAfter
        if saveAfter is not None:
            root.after_cancel(saveAfter)
        saveAfter = root.after(500, saveData)

    def commitCurrent():
        if currentEntry is None:
            return True
        text = translationText.get("1.0", "end-1c")
        if not sameCommands(currentEntry["raw"], text):
            statusVar.set("Comandos alterados: restaure as marcações azuis antes de continuar.")
            return False
        changed = False
        translation = "" if text == currentEntry["raw"] else text
        if translation != currentEntry["translation"]:
            dirtyTranslationIds.add(currentEntry["id"])
            currentEntry["translation"] = translation
            changed = True
        if reviewVar.get() != currentEntry["reviewed"]:
            dirtyReviewIds.add(currentEntry["id"])
            currentEntry["reviewed"] = reviewVar.get()
            changed = True
        if currentPosition >= 0:
            updateEntryColor(currentPosition, currentEntry)
        updateProgress()
        if changed:
            scheduleSave()
        return True

    def highlightCommands(widget, text):
        for match in tagPattern.finditer(text):
            widget.tag_add("command", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def showEntry(entry, position, refreshTranslation=True):
        nonlocal currentEntry, currentPosition, loadingEntry
        currentEntry = entry
        currentPosition = position
        entryLabel = {
            "Diálogos": "Diálogo",
            "Nomes de itens": "Nome de item",
            "Descrições de itens": "Descrição de item",
            "Nomes de habitat": "Nome de habitat",
            "Descrições de habitat": "Descrição de habitat",
            "Rótulos de habitat": "Rótulo de habitat",
            "Rótulos de construção": "Rótulo de construção",
            "Rótulos de estilo": "Rótulo de estilo",
            "Interface e sistema": "Texto de interface",
            "Objetivos, tutoriais e opções": "Objetivo, tutorial ou opção",
            "Falas curtas dos Pokémon": "Fala curta de Pokémon",
            "Preferências de habitat": "Preferência de habitat",
            "Descrições da Pokédex": "Descrição da Pokédex",
            "Classificações da Pokédex": "Classificação da Pokédex",
            "Notificações": "Notificação ou mensagem",
            "Personalização": "Opção de personalização",
            "Textos de leitura": "Texto de leitura",
            "Nomes de regiões": "Nome de região",
        }[entry["category"]]
        positionLabel.configure(text=f"{entryLabel} {position + 1:,} / {len(visibleEntries):,}    ·    ID {entry['id']}")
        originalLabel.configure(text=f"Texto original ({entry['language']})")
        originalText.configure(state="normal")
        originalText.delete("1.0", "end")
        originalText.insert("1.0", entry["original"])
        originalText.configure(state="disabled")
        if refreshTranslation:
            loadingEntry = True
            translationText.delete("1.0", "end")
            translationText.insert("1.0", entry["translation"] or entry["raw"])
            translationText.edit_reset()
            translationText.edit_modified(False)
            highlightCommands(translationText, entry["translation"] or entry["raw"])
            loadingEntry = False
        reviewVar.set(entry["reviewed"])
        statusVar.set("Comandos internos preservados no texto original.")

    def formatEntry(entry):
        text = re.sub(r"\s+", " ", entry["original"]).strip()
        return f"{entry['displayId']}  {text[:92]}"

    def applyFilter():
        nonlocal filterAfter, visibleEntries, currentEntry, currentPosition
        filterAfter = None
        if not commitCurrent():
            return
        filteredEntries = filterEntries(entries, searchVar.get(), languageVar.get(), categoryVar.get())
        currentVisible = currentEntry is not None and any(
            entry["id"] == currentEntry["id"] for entry in filteredEntries
        )
        if currentEntry and pinnedEntryId == currentEntry["id"] and not currentVisible:
            filteredEntries.append(currentEntry)
            currentVisible = True
        if currentEntry and not currentVisible and not savePendingChanges():
            return
        visibleEntries = filteredEntries
        updateProgress()
        dialogList.delete(0, "end")
        for start in range(0, len(visibleEntries), 500):
            batch = visibleEntries[start:start + 500]
            labels = [formatEntry(entry) for entry in batch]
            dialogList.insert("end", *labels)
            for offset, entry in enumerate(batch, start):
                if entry["reviewed"] or isTranslated(entry):
                    updateEntryColor(offset, entry)
        match = next((i for i, entry in enumerate(visibleEntries) if currentEntry and entry["id"] == currentEntry["id"]), 0)
        if visibleEntries:
            dialogList.selection_set(match)
            dialogList.see(match)
            sameEntry = currentEntry is not None and visibleEntries[match]["id"] == currentEntry["id"]
            showEntry(visibleEntries[match], match, refreshTranslation=not sameEntry)
        else:
            currentEntry = None
            currentPosition = -1
            positionLabel.configure(text="Nenhum texto encontrado")
            originalText.configure(state="normal")
            originalText.delete("1.0", "end")
            originalText.configure(state="disabled")
            translationText.delete("1.0", "end")

    def scheduleFilter(*_, preserveCurrent=False):
        nonlocal filterAfter, pinnedEntryId
        pinnedEntryId = currentEntry["id"] if preserveCurrent and currentEntry else None
        if filterAfter is not None:
            root.after_cancel(filterAfter)
        filterAfter = root.after(250, applyFilter)

    def onCategoryChange(_event=None):
        if categoryVar.get() == "Diálogos":
            languageSelect.configure(state="readonly")
        else:
            languageVar.set("English")
            languageSelect.configure(state="disabled")
        scheduleFilter()

    def onSelect(_event=None):
        nonlocal pinnedEntryId
        selection = dialogList.curselection()
        if not selection:
            return
        position = selection[0]
        if currentEntry and visibleEntries[position]["id"] == currentEntry["id"]:
            return
        if savePendingChanges():
            pinnedEntryId = None
            showEntry(visibleEntries[position], position)
            scheduleFilter()
        elif currentPosition >= 0:
            dialogList.selection_clear(0, "end")
            dialogList.selection_set(currentPosition)

    def moveEntry(step):
        nonlocal pinnedEntryId
        if not visibleEntries or not savePendingChanges():
            return
        position = (currentPosition + step) % len(visibleEntries)
        if position == currentPosition:
            return
        dialogList.selection_clear(0, "end")
        dialogList.selection_set(position)
        dialogList.see(position)
        pinnedEntryId = None
        showEntry(visibleEntries[position], position)
        scheduleFilter()

    def onReview():
        if not commitCurrent():
            reviewVar.set(currentEntry["reviewed"])
            return
        currentEntry["reviewed"] = reviewVar.get()
        updateProgress()
        scheduleSave()

    def onTextChanged(_event=None):
        if loadingEntry or not translationText.edit_modified():
            return
        translationText.edit_modified(False)
        if commitCurrent():
            scheduleFilter(preserveCurrent=True)
            statusVar.set("Alteração pendente de salvamento automático...")

    def onUndo(_event=None):
        try:
            translationText.edit_undo()
        except tk.TclError:
            pass
        return "break"

    def onRedo(_event=None):
        try:
            translationText.edit_redo()
        except tk.TclError:
            pass
        return "break"

    def savePendingChanges():
        nonlocal saveAfter
        if not commitCurrent():
            return False
        if saveAfter is not None:
            root.after_cancel(saveAfter)
            saveAfter = None
        return not (dirtyTranslationIds or dirtyReviewIds) or saveData()

    def closeApp():
        if not commitCurrent():
            messagebox.showwarning("Comandos internos", "Restaure as marcações azuis antes de fechar.", parent=root)
            return
        if not savePendingChanges():
            messagebox.showerror("Salvar tradução", statusVar.get(), parent=root)
            return
        root.destroy()

    def onUpdateMod():
        if not savePendingChanges():
            return

        statusVar.set("Gerando e validando o mod...")
        root.update_idletasks()
        try:
            translatedCount = generateMod()
        except Exception as error:
            statusVar.set("Falha ao atualizar o mod")
            messagebox.showerror("Atualizar Mod", str(error), parent=root)
            return

        statusVar.set(f"Mod instalado · {translatedCount:,} traduções")
        messagebox.showinfo(
            "Atualizar Mod",
            f"Mod TraducaoBR atualizado com {translatedCount:,} traduções validadas.",
            parent=root,
        )

    def onExportMod():
        outputPath = filedialog.askdirectory(title="Exportar arquivos do mod", parent=root)
        if not outputPath or not savePendingChanges():
            return
        appData = os.environ.get("APPDATA")
        installedRomfs = (
            Path(appData) / "eden" / "load" / titleId / "TraducaoBR" / "romfs"
            if appData else None
        )
        if installedRomfs and Path(outputPath).resolve() == installedRomfs.resolve():
            messagebox.showerror(
                "Exportar Mod", "Escolha uma pasta fora do mod instalado.", parent=root,
            )
            return

        statusVar.set("Exportando e validando BIN/IDX...")
        root.update_idletasks()
        try:
            translatedCount, _ = buildModFiles(Path(outputPath))
        except Exception as error:
            statusVar.set("Falha ao exportar BIN/IDX")
            messagebox.showerror("Exportar Mod", str(error), parent=root)
            return
        statusVar.set(f"BIN/IDX exportados · {translatedCount:,} traduções")
        messagebox.showinfo(
            "Exportar Mod",
            f"Arquivos BIN/IDX exportados e validados ({translatedCount:,} traduções).",
            parent=root,
        )

    categoryNumbers = {category: 0 for category in categories}
    for entry in entries:
        categoryNumbers[entry["category"]] += 1
        entry["displayId"] = f"{categoryNumbers[entry['category']]:06d}"
    updateProgress()
    searchVar.trace_add("write", scheduleFilter)
    languageVar.trace_add("write", scheduleFilter)
    categorySelect.bind("<<ComboboxSelected>>", onCategoryChange)
    dialogList.bind("<<ListboxSelect>>", onSelect)
    translationText.bind("<<Modified>>", onTextChanged)
    translationText.bind("<Control-z>", onUndo)
    translationText.bind("<Control-y>", onRedo)
    reviewCheck.configure(command=onReview)
    previousButton.configure(command=lambda: moveEntry(-1))
    nextButton.configure(command=lambda: moveEntry(1))
    ttk.Button(footerActions, text="Exportar BIN/IDX", command=onExportMod).pack(side="left", padx=(0, 8))
    ttk.Button(footerActions, text="Atualizar Mod", command=onUpdateMod).pack(side="left")
    root.protocol("WM_DELETE_WINDOW", closeApp)
    applyFilter()
    root.mainloop()


if __name__ == "__main__":
    main()
