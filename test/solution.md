Consider each number in its binary representation. For a positive integer $x$, define
$$ \operatorname{lsb}(x) $$
as the position of the rightmost $1$ bit in the binary representation of $x$, where the rightmost bit is at position $0$.

Let the number of stones in the $i$-th pile be $a_i$. Define
$$ L_i=\operatorname{lsb}(a_i). $$

A player is declared the loser if they have no valid moves, which occurs when all piles have an odd number of stones. In other words, the game will end when all $L_i = 0$.

Notice what happens if at some point all piles have the same $\operatorname{lsb}$ value, let's say $L_1 = L_2 = \cdots = L_N = c > 0$. If a player chooses pile $k$, then $a_k$ will be halved, so the value of $L_k$ becomes $c-1$. Meanwhile, every other pile $j \neq k$ will increase to $a_j + a_k/2$. Since $a_j$ is divisible by $2^c$ and $a_k/2$ is divisible by $2^{c-1}$ (but not divisible by $2^c$), their sum will definitely only be divisible by $2^{c-1}$. Consequently, the value of $L_j$ also changes to $c-1$. Therefore, a turn in this state will decrease all $L_i$ by $1$ simultaneously.

Now, for the initial stone configuration, let
$$ m=\min_{1\le i\le N} L_i. $$

### Determining the outcome of the game

* **$m$ is odd:**
  Pak Chanek can choose pile $k$ with $L_k=m$. Based on the observation above, since $a_k/2$ has its $\operatorname{lsb}$ at position $m-1$, while all $a_i$ are divisible by $2^m$, after the operation we obtain:
  $$ L_1 = L_2 = \dots = L_N = m-1. $$
  Since $m-1$ is even, this state is a losing position for the next player. Thus, Pak Chanek wins.

* **$m$ is even and $L_1=L_2=\cdots=L_N=m$:**
  For any chosen pile, after the operation all $\operatorname{lsb}$ will become $m-1$. Since $m-1$ is odd, the next player will be in a winning position as explained in the previous case. Thus, Pak Chanek loses, making Galih win.

* **$m$ is even and not all $L_i=m$:**
  In this state, there are piles with $\operatorname{lsb}(a_i) = m$ and piles with $\operatorname{lsb}(a_i) > m$. Both players can always choose a pile with $\operatorname{lsb}(a_i) > m$. After that pile is halved and added to the other piles, there will still be:
  * at least one pile with $\operatorname{lsb}(a_j) = m$;
  * at least one pile with $\operatorname{lsb}(a_j) > m$.
  
  Therefore, this state can be maintained indefinitely by both players to avoid losing, meaning the game will never reach the state where all $L_i=0$. Thus, the outcome is a draw.

### Calculating the number of configurations

The number of values $x$ ($1 \le x < 2^K$) that satisfy $\operatorname{lsb}(x) \ge i$ is $2^{K-i}-1$. Then, the number of array configurations with $m = \min_j L_j = i$ is:
$$ C_i = (2^{K-i}-1)^N - (2^{K-i-1}-1)^N. $$

The total configurations for Pak Chanek's victory ($m$ is odd) is the accumulation of $C_i$:
$$ ans_{\text{Pak Chanek}} = \sum_{\substack{0\le i<K \\ i\text{ odd}}} C_i $$

For Galih's victory, all $N$ elements must have the same even $\operatorname{lsb}$ value. Since the number of values $x$ with exactly $\operatorname{lsb}(x)=i$ is $2^{K-i-1}$, the configurations are:
$$ ans_{\text{Galih}} = \sum_{\substack{0\le i<K \\ i\text{ even}}} (2^{K-i-1})^N $$

Finally, the remainder of the total possible configurations $(2^K-1)^N$ will end in a draw:
$$ ans_{\text{Draw}} = (2^K-1)^N - ans_{\text{Pak Chanek}} - ans_{\text{Galih}}. $$

**Complexity:** $\mathcal{O}(K\log N)$ time and $\mathcal{O}(K)$ memory.