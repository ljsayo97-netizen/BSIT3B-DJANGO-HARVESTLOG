TYPE=VIEW
query=select `m`.`member_id` AS `member_id`,`m`.`member_name` AS `member_name`,`m`.`program` AS `program`,`b`.`title` AS `book_title`,`b`.`category` AS `category`,`br`.`days_borrowed` AS `days_borrowed`,`br`.`fee` AS `fee` from ((`library_b`.`borrowings` `br` join `library_b`.`members` `m` on(`br`.`member_id` = `m`.`member_id`)) join `library_b`.`books` `b` on(`br`.`book_id` = `b`.`book_id`))
md5=7f7f77ae90a8215332d6ecae2465a978
updatable=1
algorithm=0
definer_user=root
definer_host=localhost
suid=2
with_check_option=0
timestamp=0001791441447602730
create-version=2
source=SELECT\n    m.member_id,\n    m.member_name,\n    m.program,\n    b.title AS book_title,\n    b.category,\n    br.days_borrowed,\n    br.fee\nFROM borrowings br\nJOIN members m\n    ON br.member_id = m.member_id\nJOIN books b\n    ON br.book_id = b.book_id
client_cs_name=utf8mb4
connection_cl_name=utf8mb4_unicode_ci
view_body_utf8=select `m`.`member_id` AS `member_id`,`m`.`member_name` AS `member_name`,`m`.`program` AS `program`,`b`.`title` AS `book_title`,`b`.`category` AS `category`,`br`.`days_borrowed` AS `days_borrowed`,`br`.`fee` AS `fee` from ((`library_b`.`borrowings` `br` join `library_b`.`members` `m` on(`br`.`member_id` = `m`.`member_id`)) join `library_b`.`books` `b` on(`br`.`book_id` = `b`.`book_id`))
mariadb-version=100432
