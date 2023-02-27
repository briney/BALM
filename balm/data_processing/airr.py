#!/usr/bin/python
# filename: airr.py

#
# Copyright (c) 2023 Bryan Briney
# License: GNU General Public License, version 3.0 (http://opensource.org/licenses/gpl-3-0/)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software
# and associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute,
# sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or
# substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
# BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#


import os
import subprocess as sp
from typing import Optional, List, Union, Iterable

import abutils


def transform_airr(
    airr_data: Union[Iterable, str],
    output_dir: str,
    sep_token: str = "</s>",
    missing_chain_token: str = "<unk>",
    concatenate: bool = True,
    id_key: str = "sequence_id",
    sequence_key: str = "sequence_aa",
    locus_key: str = "locus",
    id_delim: str = "_",
    id_delim_occurence: int = 1,
    clustering_threshold: Optional[float] = None,
    shuffle_csv: bool = True,
    keep_paired_csv: bool = True,
    keep_sorted_airr: bool = False,
    debug: bool = False,
) -> str:
    """
    Convert one or more AIRR-formatted TSV files into RoBERTa-formatted txt files.

    Parameters
    ----------
    airr_data : Union[Iterable, str]
        Can be one of three things:
            * path to an AIRR-formatted TSV file
            * path to a directory containing one or more AIRR-formatted TSV files
            * an iterable containing one or more of either of the above.
        Required.

    output_dir : str
        Path to the output directory. If it does not exist, it will be created.
        Required.

    sep_token : str, optional
        Token used to separate heavy and light chains in the output text file.
        If all input data is unpaired and a sep token is not desired, set
        `sep_token` to ``""`` (an empty string). Default is ``"</s>"``.

    missing_chain_token : str, optional
        Token used to represent the missing chain of an unpaired sequence. If all
        input data is unpaired and a missing chain token is not desired, set
        `missing_chain_token` to ``""`` (an empty string). Default is ``"<unk>"``.

    concatenate : bool, optional
        Whether or not to concatenate all input files into a single output. Separate
        outputs will always be available in the ``output_dir/txt`` directory, regardless
        of the `concatenate` setting. Default is ``True``.

    id_key : str, optional
        Value of the sequence ID column in the input TSV files. Default is ``"sequence_id"``,
        which conforms with AIRR standards.

    sequence_key : str, optional
        Value of the amino acid sequence column in the input TSV files. Default is
        ``"sequence_aa"``, which conforms with AIRR standards.

    locus_key : str, optional
        Value of the locus column in the input TSV files. Default is ``"locus"``,
        which conforms with AIRR standards. Note that all values in the locus column must be
        one of ``"IGH"``, ``"IGK"`` or ``"IGL"``.

    id_delim : str, optional
        For paired sequences, character at which to truncate sequence IDs to obtain
        the paired sequence name. Default is ``"_"``, which is consistent with the
        naming practices of `CellRanger`_.

    id_delim_occurence : int, optional
        For paired sequences, occurance of `id_delim` at which to truncate sequence IDs to
        obtain the paired sequence name. Default is ``1``, which is consistent with the
        naming practices of `CellRanger`_.

    clustering_threshold : Optional[float], optional
        Identity threshold for sequence clustering. Default is ``None`` which skips clustering.
        Paired sequences are concatenated for clustering, meaning that two identical heavy chains
        will not cluster together if one is paired and one is unpaired.

    shuffle_csv : bool, optional
        Shuffle the order of sequences in the paired CSV file. This is typically desirable
        because sequence IDs are sorted as part of the pairing process. Default is ``True``.

    keep_paired_csv : bool, optional
        Whether or not to keep the paired CSV file, which is generated during the construction
        of the output text file. This is often useful, because it is a relatively compact representation
        of the sequences and sequence IDs used in the final output file. Default is ``True``.

    keep_sorted_airr : bool, optional
        Whether or not to keep the sorted AIRR, which is generated during the construction
        of the output text file. This file contains the same content as the input AIRR-formatted
        TSV file, but with sequences sorted by ID. Default is ``False``.

    debug : bool, optional
        If ``True``, output is much more verbose and more intermediate data files are retained.
        Default is ``False``.


    Returns
    -------
    output_dir
        Path to the output directory.


    .. _CellRanger
        https://support.10xgenomics.com/single-cell-vdj/software/pipelines/latest/what-is-cell-ranger

    """
    # process data input
    if os.path.isfile(airr_data):
        airr_data = {"": [airr_data]}
    elif os.path.isdir(airr_data):
        airr_data = {"": abutils.io.list_files(airr_data)}
    else:
        _airr_data = []
        for a in airr_data:
            if os.path.isfile(a):
                if "" not in _airr_data:
                    _airr_data[""] = []
                _airr_data[""].append(a)
            elif os.path.isdir(a):
                dirname = os.path.basename(a)
                if dirname not in _airr_data:
                    _airr_data[dirname] = []
                _airr_data[dirname].extend(abutils.io.list_files(a))
        airr_data = _airr_data
    # set up directories
    base_sort_dir = os.path.join(output_dir, "sorted")
    base_csv_dir = os.path.join(output_dir, "csv")
    base_roberta_dir = os.path.join(output_dir, "txt")
    abutils.io.makedir(base_sort_dir)
    abutils.io.makedir(base_csv_dir)
    abutils.io.makedir(base_roberta_dir)
    if clustering_threshold is not None:
        base_cluster_dir = os.path.join(output_dir, "clustered_csv")
        abutils.io.makedir(base_cluster_dir)
    # process AIRR batches
    for batch_name, airr_batch in airr_data.items():
        airr_batch = list(set(airr_batch))
        sort_dir = (
            os.path.join(base_sort_dir, batch_name) if batch_name else base_sort_dir
        )
        csv_dir = os.path.join(base_csv_dir, batch_name) if batch_name else base_csv_dir
        roberta_dir = (
            os.path.join(base_roberta_dir, batch_name)
            if batch_name
            else base_roberta_dir
        )
        if clustering_threshold is not None:
            cluster_dir = (
                os.path.join(base_cluster_dir, batch_name)
                if batch_name
                else base_cluster_dir
            )
        for airr_file in airr_data:
            positions = get_column_positions(airr_file, id_key, sequence_key, locus_key)
            to_remove = []
            # sort the input AIRR file
            sorted_file = sort_airr_file(
                airr_file=airr_file,
                sort_dir=sort_dir,
                id_pos=positions["id_pos"],
                debug=debug,
            )
            if not keep_sorted_airr:
                to_remove.append(sorted_file)
            # build a paired CSV
            paired_csv = make_paired_csv(
                sorted_file,
                csv_dir=csv_dir,
                delim=id_delim,
                delim_occurence=id_delim_occurence,
                shuffle=shuffle_csv,
                debug=debug,
                **positions,
            )
            if not keep_paired_csv:
                to_remove.append(paired_csv)
            # cluster paired sequences
            if clustering_threshold is not None:
                paired_csv = cluster_paired_csv(
                    paired_csv=paired_csv,
                    cluster_dir=cluster_dir,
                    threshold=clustering_threshold,
                )
                if not keep_paired_csv:
                    to_remove.append(paired_csv)
            # build the RoBERTa text output
            roberta_txt = build_roberta_txt(
                paired_csv=paired_csv,
                output_dir=roberta_dir,
                sep_token=sep_token,
                missing_chain_token=missing_chain_token,
            )
            # clean up
            for r in to_remove:
                os.remove(r)
        if concatenate:
            if batch_name:
                concat_file = os.path.join(output_dir, f"{batch_name}.txt")
            else:
                concat_file = os.path.join(output_dir, "output.txt")
            concatenate_roberta_txt(roberta_dir=roberta_dir, concat_file=concat_file)
    return output_dir


def sort_airr_file(
    airr_file: str, sort_dir: str, id_pos: int = 0, debug: bool = False
) -> str:
    bname = os.path.basename(airr_file).replace(".tsv", "")
    sorted_file = os.path.join(sort_dir, f"{bname}.csv")
    sort_cmd = f"tail -n +2 {airr_file} | "
    sort_cmd += f'sort -t"\t" -k {id_pos + 1},{id_pos + 1} >> {sorted_file}'
    p = sp.Popen(sort_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
    stdout, stderr = p.communicate()
    if debug:
        print(stdout)
        print(stderr)
    return sorted_file


def make_paired_csv(
    sorted_file: str,
    csv_dir: str,
    id_pos: int = 0,
    seq_pos: int = 3,
    locus_pos: int = 61,
    shuffle: bool = True,
    delim: str = "_",
    delim_occurence: int = 1,
    debug: bool = False,
):
    csv_file = os.path.join(csv_dir, os.path.basename(sorted_file))
    params = {
        "id_pos": id_pos,
        "seq_pos": seq_pos,
        "locus_pos": locus_pos,
        "delim": delim,
        "delim_occurance": delim_occurence,
    }
    prev = None
    with open(csv_file, "w") as csv:
        with open(sorted_file, "r") as f:
            for line in f:
                if not line.strip:
                    continue
                curr = CSVLine(line, **params)
                if prev is None:
                    pair = [curr]
                    prev = curr
                elif curr.name == prev.name:
                    pair.append(curr)
                    prev = curr
                else:
                    csv_line = build_csv_line(pair)
                    csv.write(csv_line + "\n")
                    pair = [curr]
                    prev = curr
            # process the last line(s)
            csv_line = build_csv_line(pair)
            csv.write(csv_line + "\n")
    if shuffle:
        shuf_cmd = f"cat {csv_file} | shuf -o {csv_file}"
        p = sp.Popen(shuf_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
        stdout, stderr = p.communicate()
        if debug:
            print(stdout)
            print(stderr)
    return csv_file


def cluster_paired_csv(paired_csv: str, cluster_dir: str, threshold: float) -> str:
    # make FASTA-formatted input for clustering
    bname = os.path.basename(paired_csv).replace(".csv", "")
    fasta_file = os.path.join(cluster_dir, f"{bname}.fasta")
    clustered_csv = os.path.join(cluster_dir, f"{bname}.csv")
    with open(fasta_file, "w") as fasta:
        with open(paired_csv, "r") as csv:
            for line in csv:
                if not (line := line.strip().split(",")):
                    continue
                name, h, k, l = line[::2]
                fasta.write(f">{name}\n{h}{k}{l}\n")
    # do clustering
    cluster_dict = abutils.tl.cluster_mmseqs(
        fasta_file=fasta_file, threshold=threshold, as_dict=True
    )
    centroid_ids = set([c["centroid_id"] for c in cluster_dict.values()])
    # build a new CSV file containing only cluster centroids
    with open(clustered_csv, "w") as clust:
        with open(paired_csv, "r") as csv:
            for line in csv:
                if line.strip():
                    name = line.strip().split(",")[0]
                    if name in centroid_ids:
                        clust.write(line)
    # remove the FASTA file used for clustering
    os.remove(fasta_file)
    return clustered_csv


def build_roberta_txt(
    paired_csv: str,
    output_dir: str,
    sep_token: str = "</s>",
    missing_chain_token: str = "<unk>",
):
    bname = os.path.basename(paired_csv).replace(".csv", "")
    roberta_file = os.path.join(output_dir, f"{bname}.txt")
    with open(roberta_file, "w") as roberta:
        with open(paired_csv, "r") as csv:
            for line in csv:
                if l := line.strip().split(","):
                    igh_seq = l[2].strip()
                    igk_seq = l[4].strip()
                    igl_seq = l[6].strip()
                    if not any([igh_seq, igk_seq, igl_seq]):
                        continue
                    if igh_seq:
                        heavy = igh_seq
                    else:
                        heavy = missing_chain_token
                    if not any([igk_seq, igl_seq]):
                        light = missing_chain_token
                    elif igk_seq:
                        light = igk_seq
                    else:
                        light = igl_seq
                roberta.write(f"{heavy}{sep_token}{light}\n")
    return roberta_file


def concatenate_roberta_txt(roberta_dir: str, concat_file: str, debug: bool = False):
    roberta_files = abutils.io.list_files(roberta_dir)
    concat_cmd = f"cat {' '.join(roberta_files)} > {concat_file}"
    p = sp.Popen(concat_cmd, stdout=sp.PIPE, stderr=sp.PIPE, shell=True)
    stdout, stderr = p.communicate()
    if debug:
        print(stdout)
        print(stderr)


def get_column_positions(
    airr_file: str,
    id_key: str = "sequence_id",
    sequence_key: str = "sequence_aa",
    locus_key: str = "locus",
) -> List[int]:
    head_cmd = f"head -n 1 {airr_file}"
    p = sp.Popen(head_cmd, stdout=sp.PIPE, shell=True)
    stdout = p.communicate()
    header = stdout.decode("utf-8").strip().split("\t")
    id_pos = header.index(id_key)
    seq_pos = header.index(sequence_key)
    locus_pos = header.index(locus_key)
    return {"id_pos": id_pos, "seq_pos": seq_pos, "locus_pos": locus_pos}


def build_csv_line(lines) -> str:
    line_data = [lines[0].name]
    for locus in ["IGH", "IGK", "IGL"]:
        seqs = [l for l in lines if l.locus == locus]
        if seqs:
            seq = seqs[0]
            line_data.append(seq.id)
            line_data.append(seq.seq)
        else:
            line_data.append("")
            line_data.append("")
    return ",".join(line_data)


class CSVLine:
    def __init__(
        self,
        line: str,
        id_pos: int = 0,
        seq_pos: int = 3,
        locus_pos: int = 61,
        delim: str = "_",
        delim_occurrence: int = 1,
    ):
        self.raw_line = line
        self.line = line.strip().split("\t")
        self.id_pos = id_pos
        self.seq_pos = seq_pos
        self.locus_pos = locus_pos
        self.delim = delim
        self.delim_occurrence = delim_occurrence

    @property
    def id(self) -> str:
        return self.line[self.id_pos]

    @property
    def name(self) -> str:
        return self.delim.join(self.line)[self.id_pos].split(self.delim)[
            : self.delim_occurrence
        ]

    @property
    def seq(self) -> str:
        return self.line[self.seq_pos]

    @property
    def locus(self) -> str:
        return self.line[self.locus_pos]
