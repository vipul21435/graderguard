# Normalize a name list

Write `normalize.py` in the workspace root. Run as `python normalize.py` from the workspace
root, it must read `data/names.txt` and write `out/names.txt` where:

- each line is trimmed and every run of whitespace becomes a single space;
- every word is capitalized (first letter upper case, the rest lower case);
- blank lines and later duplicates (compared after normalizing) are dropped, keeping the
  order in which names first appear;
- every line, including the last, ends with a newline.
