Consider the number of $0$s in $a$.

* **If there are no $0$s in $a$:** Any partitioning would result in each set having a $\text{MEX}$ of $0$, trivially satisfying the condition.
* **If there is one $0$ in $a$:** Any partitioning would result in exactly $1$ set having a $\text{MEX}$ greater than $0$, which would violate the condition.
* **If there are at least two $0$s in $a$:** Put the first $0$ in $A$, any other zeroes in $B$, and all non-zero elements in $C$. This makes $\text{MEX}(A) = \text{MEX}(B) = 1$ and $\text{MEX}(C) = 0$, so:
  $$ \text{MEX}(A) + \text{MEX}(B) + \text{MEX}(C) = 2 \ge 2 \cdot \max(\text{MEX}(A), \text{MEX}(B), \text{MEX}(C)) = 2 $$