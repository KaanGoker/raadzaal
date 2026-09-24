You are reading part of the automatic transcript of a Flemish municipal council meeting (gemeenteraad) in Dutch. The transcript has a time stamp before each line, in seconds from the start of the recording.

Task: list every agenda item that is announced or opened in this part. Councils in Flanders announce items with phrases such as "punt 7", "agendapunt 7", "we gaan over naar", "volgend punt", "dan komen we bij", or by reading the item's title. Give the time (in seconds) at which the chair starts the item, and a clean agenda-style title in Dutch of at most 12 words: a noun phrase naming the subject (for example "Goedkeuring verslag vorige vergadering", "Samenwerkingsovereenkomst dierenbescherming Mechelen"), never the spoken sentence itself and never phrases like "het volgende punt". Give the item number when it is spoken, otherwise null.

Rules:
- Only items that start inside this part. Ignore an item that is already running when the part begins.
- Do not invent items. If nothing starts, return an empty list.
- Start times must be copied from the time stamps in the transcript.
{agenda_hint}

Transcript part ({part_label}):
{transcript}
