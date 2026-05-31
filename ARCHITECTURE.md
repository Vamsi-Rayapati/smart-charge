


#### Station Selection Algo
```
Algo 1 ❌
1. Find all possible paths for each bus and find valid one's which are following constratints.
2. Select path with less stops. (DUMB)
3. Then consider this path bus moves 
4. When collison happens at station find path with good score (less penality)

At station we are ordering properly but we deciding path in upfront without current load.

Hmmm.. need to balance both path selection and bus order at station

Algo 2  ✅

1. Find all possible paths for each bus and find valid one's which are following constratints.
2. Select path considering the load at each station.
3. 

```