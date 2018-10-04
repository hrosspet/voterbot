import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def array_to_string(data, i_range, j_range):
    res = ""
    for i in range(i_range):
        for j in range(j_range):
            res += str(data[i][j]) + " "
        res += "\n"
    return res


def print_2d(data, i_range, j_range):
    for i in range(i_range):
        for j in range(j_range):
            print(str(data[i][j]), end=" ")
        print()


def get_char_ind_dicts(alphabet):
    logger.debug("Reserving 0 for uknown chars")

    char2ind = defaultdict(lambda: 0)
    char2ind.update({c: i + 1 for i, c in enumerate(alphabet)})

    ind2char = defaultdict(lambda: "")
    ind2char.update({i + 1: c for i, c in enumerate(alphabet)})

    return char2ind, ind2char
