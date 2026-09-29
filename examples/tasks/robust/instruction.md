# Run-length encoding

Write `rle.py` in the workspace root. Run as `python rle.py` from the workspace root, it must
read `data/input.txt` and write `out/encoded.txt`.

The input is a string of lower-case letters `a` to `z`; a single trailing newline, if present,
is not part of the string. The output replaces every maximal run of one letter with the letter
followed by the run length in decimal, then one newline. For example `aaabcc` becomes
`a3b1c2`. An empty string encodes to just the newline.

The tests in `tests/` show how your work will be checked; they use inputs you have not seen.
