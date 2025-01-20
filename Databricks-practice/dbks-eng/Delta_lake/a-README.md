Delta lake is an open source framework/project that allows for build lakehouse platform
**https://docs.databricks.com/en/delta/index.html**
- Open spource
- Build upon standard data format (Parquet)
- Optimized for cloud object storage (Cheap, Durable and Scalable)
- Built for Scalable metadata handling

<!-- Objective of Delta -->
- To Quickly returning the data point query in vast changing dataset
- It decompute storage cost from compute compare to traditional Relational Sources
- Powering your data across the org , through different app without replicate the data

**DELTA LAKE PROVIDE ACID SCOPE AT TABLE LEVEL**
- ATOMICITY -> transactions are treated as single unit  either succeed together or Fail together and rolled back
- CONSISTENCY - Only Valid data stored, which must be valid according rules such as  
   constraint, cascade, triggers.  requirement that any given database transaction change affects data only in an acceptable manner defined by the rules set by the database's developer. For example, the column in a database may have only two values true or fals
- ISOLATION - Transaction activities should be treated in Isolation without overlapping on each other
    to maintain database integrity and prevent conflicts. It ensures that each transaction sees a consistent view of the data, even when other transactions are running concurrently
- DURABILITY - When Changes are made they are permanent

**PROBLEM SOLVED BY ACID**
- hard to Append
- Modifying of Existing data difficult
- Job Failing Mid Way
- Real- time Operations
- Costly to keep history data versions