## Description

Pak Chanek is competing in an annual strategy-game tournament in Chaneknesia. In the preliminary round, he is randomly paired with Galih, a fellow competitor he has just met at the venue. The game they are about to play uses $N$ piles of stones, where pile $i$ initially has $a_i$ stones. The two players take turns, and since Pak Chanek registered first, he always gets the first turn.

On a turn, a player must choose a pile index $i$ ($1 \le i \le N$) such that the number of stones in pile $i$ is even. After the player chooses index $i$, the piles change as follows:

* The number of stones in pile $i$ is halved (becoming $\frac{a_i}{2}$).
* For every other pile $j$ ($j \neq i$), the number of stones increases by $\frac{a_i}{2}$ (becoming $a_j + \frac{a_i}{2}$).

A player who has no valid move on their turn (that is, when every pile has an odd number of stones) is declared the loser. If after $10^{100}$ moves the game still has not ended (neither player has lost), the game is declared a draw.

While waiting for the match to begin, Pak Chanek grows curious: out of every possible starting configuration, how many would make him win, how many would make Galih win, and how many would end in a draw?

You are given two integers, $N$ and $K$. There are $2^K - 1$ possible values for each $a_i$, namely the range $1 \le a_i < 2^K$. Considering every possible starting value for the array $a$ of length $N$, count, respectively, how many initial configurations result in:

1. Pak Chanek winning for certain.
2. Galih winning for certain.
3. The game ending in a draw.

Since the answer can be very large, output all three answers modulo $998\ 422\ 353$. Assume both players always play optimally to win, or to force a draw if they cannot win.

## Constraints

* $1 \le N, K \le 100\ 000$