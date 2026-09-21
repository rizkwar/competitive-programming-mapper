## D. MEX Multiset

**time limit per test:** 2 seconds  
**memory limit per test:** 256 megabytes  

You are given an array $a_1, a_2, \ldots, a_n$. There exist $3$ initially empty multisets $A, B, C$, and for each index $i$ ($1 \le i \le n$), you may put $a_i$ into exactly one of $A$, $B$, or $C$.

Determine whether it is possible to put the elements into the multisets such that $\text{MEX}(A) + \text{MEX}(B) + \text{MEX}(C) \ge 2 \cdot \max(\text{MEX}(A), \text{MEX}(B), \text{MEX}(C))^*$. If so, output a construction that achieves this.

$^*$ $\text{MEX}(D)$ is defined as the smallest non-negative integer that is not present in the set $D$. For example, $\text{MEX}([1, 2, 0, 5]) = 3$, and $\text{MEX}([1, 2, 4, 9]) = 0$. The $\text{MEX}$ of an empty set is $0$.

### Input

The first line of each input contains $t$ ($1 \le t \le 10^4$) — the number of test cases.

The first line of each test case contains $n$ ($3 \le n \le 2 \cdot 10^5$) — the length of $a$.

The second line of each test case contains $a_1, a_2, \ldots, a_n$ ($0 \le a_i \le 10^9$) — the array $a$.

It is guaranteed that the sum of $n$ over all test cases does not exceed $2 \cdot 10^5$.

### Output

If a valid distribution of elements into the multisets exists, output `YES`. Otherwise, output `NO`.

If the answer is `YES`, output a string $s$ of length $n$ on a new line, such that $s_i = \text{A}$ if the $i$-th element was put into the multiset $A$, $s_i = \text{B}$ if the $i$-th element was put into the multiset $B$, and $s_i = \text{C}$ if the $i$-th element was put into the multiset $C$.

You can output the answer in any case (upper or lower). For example, the strings `YES`, `yes`, `yEs`, and `Yes` will be recognized as positive responses, and the strings `NO`, `no`, `No` will be recognized as negative responses. Additionally, the strings `AABCAAA`, `aabcaaa`, and `aaBcaaa` will be recognized as the same answer.

If there are multiple possible outputs, output any.