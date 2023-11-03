from airflow import DAG
from airflow.operators.postgres_operator import PostgresOperator
from datetime import datetime, timedelta

# Define default arguments for the DAG
default_args = {
    'owner': 'mozes',
    'depends_on_past': False,
    'start_date': datetime(2023, 11, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Create a DAG instance
dag = DAG(
    'task4__datamodel_creation',
    default_args=default_args,
    schedule_interval='@daily',  # Run daily
    catchup=False,
    max_active_runs=1,
)

# Define SQL queries for table deletion and creation
delete_table_sql = "DROP TABLE IF EXISTS task4_datamodel RESTRICT;"
create_table_sql = """
create table task4_datamodel as (
	with applications_cte as (
		select
			id as application_id,
			created_at as application_created_at,
			customer_id,
			loan_id
		from applications	
	),
	loans_cte as (
		select 
			id as loan_id,
			customer_id,
			status
		from loans
	),
	cycles_cte as (
		select 
			id as cycle_id,
			created_at as cycle_created_at,
			loan_id,
			customer_id,
			dpd,
			status
		from cycles
	),
	cycles_30_day_dpd as (
		select
			c1.created_at as cycle_created_at,
			c1.loan_id,
			c1.customer_id,
			c1.dpd,
			round(avg(c2.dpd),2) as avg_dpd_30_days,
			max(c2.dpd) as max_dpd_30_days
		from cycles as c1
		LEFT JOIN cycles as c2
		ON c1.loan_id = c2.loan_id
		AND c1.customer_id = c2.customer_id
		AND c2.created_at >= c1.created_at - INTERVAL '30 days'
		AND c2.created_at < c1.created_at
		GROUP BY c1.created_at, c1.loan_id, c1.customer_id, c1.dpd
		ORDER BY c1.loan_id, c1.customer_id, c1.created_at
	),
	cycles_60_day_dpd as (
		select
			c1.created_at as cycle_created_at,
			c1.loan_id,
			c1.customer_id,
			c1.dpd,
			round(avg(c2.dpd),2) as avg_dpd_60_days,
			max(c2.dpd) as max_dpd_60_days
		from cycles as c1
		LEFT JOIN cycles as c2
		ON c1.loan_id = c2.loan_id
		AND c1.customer_id = c2.customer_id
		AND c2.created_at >= c1.created_at - INTERVAL '60 days'
		AND c2.created_at < c1.created_at
		GROUP BY c1.created_at, c1.loan_id, c1.customer_id, c1.dpd
		ORDER BY c1.loan_id, c1.customer_id, c1.created_at
	),
	loans_and_applications as (
		select 
			a.application_id,
			a.application_created_at,
			a.customer_id,
			a.loan_id,
			count(a.application_id) over (partition by a.customer_id order by a.application_created_at rows between unbounded preceding and 1 preceding) as nr_of_applications_before,
			count(a.loan_id) over (partition by a.customer_id order by a.application_created_at rows between unbounded preceding and 1 preceding) as nr_of_loans_before
		from applications_cte as a
		order by 
			a.customer_id , 
			a.application_created_at
	),
	paid_unpaid_cycles as (
		select 
			a.*,
			c.cycle_created_at,
			sum(
				case 
					when c.status = 'paid'
					then 1
					else 0
				end
			) over (partition by a.customer_id order by c.cycle_created_at rows between unbounded preceding and 1 preceding) as paid_cycles_before,
			sum(
				case 
					when c.status <> 'paid'
					then 1
					else 0
				end
			) over (partition by a.customer_id order by c.cycle_created_at rows between unbounded preceding and 1 preceding) as unpaid_cycles_before
		from loans_and_applications as a
		left join cycles_cte as c
			on a.customer_id = c.customer_id
			and a.loan_id = c.loan_id
	)
	select 
		puc.*,
		avg_dpd_30_days,
		max_dpd_30_days,
		avg_dpd_60_days,
		max_dpd_60_days
	from paid_unpaid_cycles as puc
	left join cycles_30_day_dpd c30
	on puc.loan_id = c30.loan_id
	and puc.customer_id = c30.customer_id
	and puc.cycle_created_at = c30.cycle_created_at
	left join cycles_60_day_dpd c60
	on puc.loan_id = c60.loan_id
	and puc.customer_id = c60.customer_id
	and puc.cycle_created_at = c60.cycle_created_at
);
"""

# Task to delete the table if it exists
delete_table_task = PostgresOperator(
    task_id='delete_table',
    postgres_conn_id='anyfin_postgres_connection',
    sql=delete_table_sql,
    dag=dag,
    autocommit=True,
)

# Task to create a new table
create_table_task = PostgresOperator(
    task_id='create_table',
    postgres_conn_id='anyfin_postgres_connection',
    sql=create_table_sql,
    dag=dag,
    autocommit=True,
)

# Set task dependencies
delete_table_task >> create_table_task

# if __name__ == "__main__":
#     dag.cli()
